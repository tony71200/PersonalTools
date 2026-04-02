# /mnt/data/softChoice.py
"""
Sử dụng nhận dạng khuôn mặt để lọc các ảnh có mặt người và gộp các ảnh gần giống thành 1 nhóm.

Changes:
- If user answers 'n' at quota prompt => manual quotas input (no exit).
- Always move no-face images to `noFaceFolder/`.
- If CLIP embedding or KMeans fails => safe fallback (no crash).
- Fixed insightface bbox width/height calculation (x2-x1, y2-y1).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set, Tuple

import cv2
import numpy as np
import torch
from PIL import Image
from sklearn.cluster import KMeans
from transformers import CLIPModel, CLIPProcessor

import insightface
from insightface.app import FaceAnalysis


VALID_EXTS = (".jpg", ".jpeg", ".png")
TOTAL_IMAGES = 1000


def get_images(folder: str) -> List[str]:
    return [
        f
        for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith(VALID_EXTS)
    ]


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_move(src: str, dst_dir: str) -> None:
    """
    Move src into dst_dir. If filename exists, append an incrementing suffix.
    """
    ensure_dir(dst_dir)
    base = os.path.basename(src)
    name, ext = os.path.splitext(base)
    dst = os.path.join(dst_dir, base)

    if not os.path.exists(dst):
        shutil.move(src, dst)
        return

    i = 1
    while True:
        cand = os.path.join(dst_dir, f"{name}_{i}{ext}")
        if not os.path.exists(cand):
            shutil.move(src, cand)
            return
        i += 1


def detect_face(img_path: str, det_model: FaceAnalysis, min_face_size: int = 40) -> bool:
    img = cv2.imread(img_path)
    if img is None:
        return False

    faces = det_model.get(img)
    if not faces:
        return False

    # insightface bbox: [x1, y1, x2, y2]
    largest = max(faces, key=lambda x: max(0.0, (x.bbox[2] - x.bbox[0])) * max(0.0, (x.bbox[3] - x.bbox[1])))
    w = float(largest.bbox[2] - largest.bbox[0])
    h = float(largest.bbox[3] - largest.bbox[1])
    return w > min_face_size and h > min_face_size


def get_clip_embeddings(
    img_paths: Sequence[str],
    processor: CLIPProcessor,
    model: CLIPModel,
    device: str,
    batch_size: int = 32,
) -> np.ndarray:
    if not img_paths:
        raise ValueError("img_paths is empty")

    features: List[np.ndarray] = []
    for i in range(0, len(img_paths), batch_size):
        batch_files = img_paths[i : i + batch_size]
        images = [Image.open(f).convert("RGB") for f in batch_files]
        inputs = processor(images=images, return_tensors="pt", padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            emb = model.get_image_features(**inputs)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            features.append(emb.detach().cpu().numpy())

    return np.vstack(features)


def redistribute_quotas(folder_lens: Sequence[int], quotas: List[int], total_images: int) -> List[int]:
    """
    Ensure quotas do not exceed folder size, and keep sum(quotas) == total_images when possible.
    """
    quotas = list(quotas)
    total = sum(quotas)

    for i in range(len(quotas)):
        if folder_lens[i] < quotas[i]:
            total -= quotas[i] - folder_lens[i]
            quotas[i] = folder_lens[i]

    quota_spots = [i for i in range(len(quotas)) if folder_lens[i] > quotas[i]]
    idx = 0
    while total < total_images:
        if not quota_spots:
            break
        quotas[quota_spots[idx % len(quota_spots)]] += 1
        total += 1
        idx += 1

    return quotas


def manual_quotas(
    folders: Sequence[str],
    folder_lens: Sequence[int],
    total_images: int,
) -> List[int]:
    """
    Ask user to input quota (number of images to keep) for each folder.

    Rules:
    - Each quota must be between 0 and folder_lens[i].
    - By default, accept empty input => 0.
    - If sum != total_images, ask whether to:
      - auto-fix by scaling down/up where possible
      - or accept as-is (keeps your sum; useful if you don't need exactly total_images)
    """
    quotas: List[int] = []
    print("\nNhập quota thủ công cho từng folder (số ảnh giữ lại).")
    for i, (folder, max_n) in enumerate(zip(folders, folder_lens), start=1):
        while True:
            raw = input(f"  {i}. {folder} (0..{max_n}) = ").strip()
            if raw == "":
                q = 0
            else:
                try:
                    q = int(raw)
                except ValueError:
                    print("    -> Vui lòng nhập số nguyên.")
                    continue

            if 0 <= q <= max_n:
                quotas.append(q)
                break
            print(f"    -> Không hợp lệ. Phải nằm trong 0..{max_n}.")

    s = sum(quotas)
    print(f"\nTổng quota bạn nhập = {s} (mục tiêu = {total_images}).")

    if s == total_images:
        return quotas

    choice = input("Bạn muốn tự động điều chỉnh để khớp tổng mục tiêu không? (y/n): ").strip().lower()
    if choice != "y":
        return quotas

    # Auto-adjust:
    # - If sum too high: reduce from folders that have quota>0, starting from largest quota.
    # - If sum too low: add to folders that still have capacity, round-robin.
    quotas = quotas[:]
    if s > total_images:
        need_reduce = s - total_images
        order = sorted(range(len(quotas)), key=lambda i: quotas[i], reverse=True)
        for i in order:
            if need_reduce <= 0:
                break
            reducible = quotas[i]
            if reducible <= 0:
                continue
            d = min(reducible, need_reduce)
            quotas[i] -= d
            need_reduce -= d

    elif s < total_images:
        need_add = total_images - s
        spots = [i for i in range(len(quotas)) if quotas[i] < folder_lens[i]]
        idx = 0
        while need_add > 0 and spots:
            i = spots[idx % len(spots)]
            if quotas[i] < folder_lens[i]:
                quotas[i] += 1
                need_add -= 1
            idx += 1
            spots = [j for j in spots if quotas[j] < folder_lens[j]]

    print("\nQuota sau điều chỉnh:")
    for i, q in enumerate(quotas, start=1):
        print(f"  {i}. {folders[i-1]}: {q} ảnh")
    print(f"Tổng = {sum(quotas)}")
    return quotas


def select_diverse_images(
    good_imgs: Sequence[str],
    quota: int,
    clip_processor: CLIPProcessor,
    clip_model: CLIPModel,
    device: str,
) -> Set[str]:
    """
    Try CLIP+KMeans selection. On failure, fallback to deterministic first-N.
    """
    if quota <= 0 or not good_imgs:
        return set()

    if len(good_imgs) <= quota:
        return set(good_imgs)

    try:
        embs = get_clip_embeddings(good_imgs, clip_processor, clip_model, device)
        kmeans = KMeans(n_clusters=quota, random_state=0, n_init=4)
        labels = kmeans.fit_predict(embs)
        centers = kmeans.cluster_centers_

        selected: Set[str] = set()
        for i in range(quota):
            cluster_indices = np.where(labels == i)[0]
            if cluster_indices.size == 0:
                continue
            dists = np.linalg.norm(embs[cluster_indices] - centers[i], axis=1)
            idx = int(cluster_indices[int(np.argmin(dists))])
            selected.add(good_imgs[idx])

        # If some clusters ended empty, fill remaining from left to right
        if len(selected) < quota:
            for p in good_imgs:
                if p not in selected:
                    selected.add(p)
                    if len(selected) == quota:
                        break

        return selected
    except Exception as e:
        print(f"  ! Lỗi embedding/kmeans: {type(e).__name__}: {e}")
        print("  ! Fallback: chọn ảnh theo thứ tự (first-N).")
        return set(good_imgs[:quota])


def main() -> None:
    num_folders = int(input("Nhập số lượng folder cần tính toán: ").strip())
    folders: List[str] = []

    for i in range(num_folders):
        path = input(f"Nhập đường dẫn đến folder {i+1}: ").strip()
        while not os.path.isdir(path):
            print("Đường dẫn không hợp lệ. Nhập lại.")
            path = input(f"Nhập đường dẫn đến folder {i+1}: ").strip()
        folders.append(path)

    folder_imgs: List[List[str]] = []
    for folder in folders:
        imgs = get_images(folder)
        folder_imgs.append(imgs)

    folder_lens = [len(imgs) for imgs in folder_imgs]

    print("\nSố lượng ảnh mỗi folder:")
    for i, (folder, count) in enumerate(zip(folders, folder_lens), start=1):
        print(f"{i}. {folder}: {count} ảnh")

    quotas = [TOTAL_IMAGES // num_folders] * num_folders
    remain = TOTAL_IMAGES - sum(quotas)
    for i in range(remain):
        quotas[i] += 1

    quotas = redistribute_quotas(folder_lens, quotas, TOTAL_IMAGES)

    print("\nQuota phân bổ mỗi folder (auto):")
    for i, q in enumerate(quotas, start=1):
        print(f"{i}. {folders[i-1]}: {q} ảnh")

    agree = input("Bạn có đồng ý với quota này không? (y/n): ").strip().lower()
    if agree != "y":
        quotas = manual_quotas(folders, folder_lens, TOTAL_IMAGES)

    print("\nĐang tải model face detection & CLIP...")
    try:
        det_model = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider"])
        det_model.prepare(ctx_id=0, det_size=(640, 640))
        print("Đang dùng GPU (CUDAExecutionProvider)")
    except Exception as e:
        print(f"Không thể dùng GPU, chuyển sang CPU... ({type(e).__name__}: {e})")
        det_model = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        det_model.prepare(ctx_id=0, det_size=(640, 640))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    clip_model = (
        CLIPModel.from_pretrained(
            "openai/clip-vit-base-patch32",
            from_tf=False,
            torch_dtype=torch.float32,
            use_safetensors=True,
        )
        .to(device)
        .eval()
    )
    clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    for folder, imgs, quota in zip(folders, folder_imgs, quotas):
        print(f"\nXử lý folder {folder}...")
        img_paths = [os.path.join(folder, f) for f in imgs]

        no_face_folder = os.path.join(folder, "noFaceFolder")
        nontrain_folder = os.path.join(folder, "nonTrainFolder")
        ensure_dir(no_face_folder)
        ensure_dir(nontrain_folder)

        good_imgs: List[str] = []
        no_face_imgs: List[str] = []

        for p in img_paths:
            try:
                if detect_face(p, det_model):
                    good_imgs.append(p)
                else:
                    no_face_imgs.append(p)
            except Exception:
                # If face detection fails on an image, treat it as no-face to keep pipeline safe.
                no_face_imgs.append(p)

        for p in no_face_imgs:
            safe_move(p, no_face_folder)

        print(f"  > Có {len(good_imgs)} ảnh có mặt người rõ.")
        print(f"  > Chuyển {len(no_face_imgs)} ảnh không có mặt người sang noFaceFolder/.")

        selected = select_diverse_images(good_imgs, quota, clip_processor, clip_model, device)

        moved_nontrain = 0
        for p in good_imgs:
            if p not in selected:
                safe_move(p, nontrain_folder)
                moved_nontrain += 1

        print(
            f"  > Đã chọn {len(selected)} ảnh (có mặt người), "
            f"di chuyển {moved_nontrain} ảnh sang nonTrainFolder/."
        )

    print("\nHoàn thành!")


if __name__ == "__main__":
    main()