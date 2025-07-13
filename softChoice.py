import os
import cv2
import shutil
import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import numpy as np
from sklearn.cluster import KMeans
import insightface
from insightface.app import FaceAnalysis

# ---- Các hàm tiện ích ----
def get_images(folder):
    valid_exts = ('.jpg', '.jpeg', '.png')
    return [f for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith(valid_exts)]

def detect_face(img_path, det_model, min_face_size=40):
    img = cv2.imread(img_path)
    if img is None:
        return False
    faces = det_model.get(img)
    if faces is None or len(faces) == 0:
        return False
    # Chọn khuôn mặt lớn nhất
    largest = max(faces, key=lambda x: x.bbox[2]*x.bbox[3])
    w, h = largest.bbox[2], largest.bbox[3]
    return w > min_face_size and h > min_face_size

def get_clip_embeddings(img_paths, processor, model, device):
    batch_size = 32
    features = []
    for i in range(0, len(img_paths), batch_size):
        batch_files = img_paths[i:i+batch_size]
        images = [Image.open(f).convert("RGB") for f in batch_files]
        inputs = processor(images=images, return_tensors="pt", padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            emb = model.get_image_features(**inputs)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            features.append(emb.cpu().numpy())
    return np.vstack(features)

# ---- Main program ----
def main():
    # Step 1: Nhập số folder và đường dẫn
    num_folders = int(input("Nhập số lượng folder cần tính toán: "))
    folders = []
    for i in range(num_folders):
        path = input(f"Nhập đường dẫn đến folder {i+1}: ").strip()
        while not os.path.isdir(path):
            print("Đường dẫn không hợp lệ. Nhập lại.")
            path = input(f"Nhập đường dẫn đến folder {i+1}: ").strip()
        folders.append(path)

    # Step 2: Đếm số lượng ảnh mỗi folder (không tính subfolder)
    all_imgs = []
    folder_imgs = []
    for folder in folders:
        imgs = get_images(folder)
        folder_imgs.append(imgs)
        all_imgs += imgs

    folder_lens = [len(imgs) for imgs in folder_imgs]

    print("\nSố lượng ảnh mỗi folder:")
    for i, (folder, count) in enumerate(zip(folders, folder_lens)):
        print(f"{i+1}. {folder}: {count} ảnh")

    # Step 3: Chia quota 1000 ảnh cho các folder
    TOTAL_IMAGES = 1000
    quotas = [TOTAL_IMAGES // num_folders] * num_folders
    remain = TOTAL_IMAGES - sum(quotas)
    for i in range(remain):  # chia đều phần dư
        quotas[i] += 1

    # Điều chỉnh nếu folder nào ít hơn quota ban đầu
    def redistribute_quotas(folder_lens, quotas):
        total = sum(quotas)
        for i in range(len(quotas)):
            if folder_lens[i] < quotas[i]:
                total -= quotas[i] - folder_lens[i]
                quotas[i] = folder_lens[i]
        # Chia lại phần dư
        quota_spots = [i for i in range(len(quotas)) if folder_lens[i] > quotas[i]]
        idx = 0
        while total < TOTAL_IMAGES:
            if not quota_spots: break
            quotas[quota_spots[idx % len(quota_spots)]] += 1
            total += 1
            idx += 1
        return quotas

    quotas = redistribute_quotas(folder_lens, quotas)
    print("\nQuota phân bổ mỗi folder:")
    for i, q in enumerate(quotas):
        print(f"{i+1}. {folders[i]}: {q} ảnh")

    agree = input("Bạn có đồng ý với quota này không? (y/n): ").lower()
    if agree != 'y':
        print("Kết thúc.")
        return

    # Step 4: Chuẩn bị model face & CLIP
    print("\nĐang tải model face detection & CLIP...")
    try:
        det_model = FaceAnalysis(name="buffalo_l", providers=['CUDAExecutionProvider'])
        det_model.prepare(ctx_id=0, det_size=(640, 640))
        print('Đang dùng GPU (CUDAExecutionProvider)')
    except Exception as e:
        print('Không thể dùng GPU, chuyển sang CPU...')
        det_model = FaceAnalysis(name="buffalo_l", providers=['CPUExecutionProvider'])
        det_model.prepare(ctx_id=0, det_size=(640, 640))
    # det_model = insightface.model_zoo.get_model('buffalo_l')
    # det_model.prepare(ctx_id=0 if torch.cuda.is_available() else -1)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32", from_tf=False, torch_dtype=torch.float32, use_safetensors=True).to(device)
    clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    # Step 5: Duyệt từng folder, chọn ảnh tốt nhất
    for folder, imgs, quota in zip(folders, folder_imgs, quotas):
        print(f"\nXử lý folder {folder}...")
        img_paths = [os.path.join(folder, f) for f in imgs]
        # 1. Lọc ảnh có mặt người rõ
        good_imgs = []
        for p in img_paths:
            if detect_face(p, det_model):
                good_imgs.append(p)
        print(f"  > Có {len(good_imgs)}/{len(img_paths)} ảnh có mặt người rõ.")
        # 2. Nếu số lượng <= quota thì giữ nguyên
        if len(good_imgs) <= quota:
            selected = set(good_imgs)
        else:
            # 3. Dùng CLIP lấy embedding
            print("  > Đang tính embedding CLIP và phân nhóm ảnh đa dạng...")
            embs = get_clip_embeddings(good_imgs, clip_processor, clip_model, device)
            # 4. Cluster chọn ra quota ảnh đa dạng nhất
            kmeans = KMeans(n_clusters=quota, random_state=0, n_init=4)
            labels = kmeans.fit_predict(embs)
            centers = kmeans.cluster_centers_
            # Chọn mỗi cluster ảnh gần tâm nhất
            selected = set()
            for i in range(quota):
                cluster_indices = np.where(labels == i)[0]
                dists = np.linalg.norm(embs[cluster_indices] - centers[i], axis=1)
                idx = cluster_indices[np.argmin(dists)]
                selected.add(good_imgs[idx])
        # 5. Di chuyển ảnh không được chọn sang nonTrainFolder
        nontrain = os.path.join(folder, "nonTrainFolder")
        os.makedirs(nontrain, exist_ok=True)
        for p in img_paths:
            if p not in selected:
                shutil.move(p, os.path.join(nontrain, os.path.basename(p)))
        print(f"  > Đã chọn {len(selected)} ảnh, di chuyển {len(img_paths)-len(selected)} ảnh sang nonTrainFolder.")

    print("\nHoàn thành!")

if __name__ == "__main__":
    main()
