from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import cv2

from .models import read_rgb_pil
from .quality import (
    calc_quality_score,
    dhash_from_gray,
    score_composition,
    score_exposure,
    score_face_size,
    score_resolution,
    score_sharpness,
)
from .types import Config, FolderResult, ImageMetrics, RuntimeModels
from .utils import list_images, log


def compute_clip_embeddings(items: List[ImageMetrics], runtime: RuntimeModels, cfg: Config) -> None:
    if not runtime.clip_enabled or not items:
        return

    import torch

    valid_items = []
    for item in items:
        try:
            img = read_rgb_pil(Path(item.path))
            valid_items.append((item, img))
        except Exception:
            item.notes = (item.notes + " | clip_read_fail").strip(" |")

    batch_size = max(1, cfg.clip_batch_size)
    for start in range(0, len(valid_items), batch_size):
        batch = valid_items[start:start + batch_size]
        batch_items = [x[0] for x in batch]
        batch_images = [x[1] for x in batch]
        try:
            inputs = runtime.clip_processor(images=batch_images, return_tensors="pt")
            inputs = {k: v.to(runtime.clip_device) for k, v in inputs.items()}
            with torch.no_grad():
                feats = runtime.clip_model.get_image_features(**inputs)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                arr = feats.detach().cpu().numpy()
            for i, item in enumerate(batch_items):
                item.clip_embedding = arr[i]
        except Exception as exc:
            for item in batch_items:
                item.notes = (item.notes + f" | clip_embed_fail:{type(exc).__name__}").strip(" |")


def analyze_one_image(path: Path, folder_name: str, runtime: RuntimeModels, cfg: Config) -> ImageMetrics:
    item = ImageMetrics(path=str(path), folder_name=folder_name, file_name=path.name)
    img = cv2.imread(str(path))
    if img is None:
        item.reject_reason = "read_error"
        return item

    item.readable = True
    h, w = img.shape[:2]
    item.width = int(w)
    item.height = int(h)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    item.sharpness_score = score_sharpness(gray)
    item.exposure_score = score_exposure(gray)
    item.resolution_score = score_resolution(w, h)
    item.dhash = dhash_from_gray(gray)

    faces = runtime.det_model.get(img)
    item.face_count = len(faces)

    if not faces:
        item.reject_reason = "no_face"
        item.quality_score = calc_quality_score(
            0.0,
            item.sharpness_score,
            item.exposure_score,
            0.0,
            item.resolution_score,
        )
        return item

    item.face_detected = True
    largest = max(
        faces,
        key=lambda x: max(0.0, float(x.bbox[2] - x.bbox[0])) * max(0.0, float(x.bbox[3] - x.bbox[1])),
    )
    x1, y1, x2, y2 = map(float, largest.bbox[:4])
    face_w = max(0.0, x2 - x1)
    face_h = max(0.0, y2 - y1)
    item.face_bbox = (x1, y1, x2, y2)
    item.face_area_ratio = (face_w * face_h) / float(max(1, w * h))
    item.face_size_score = score_face_size(item.face_area_ratio, face_w, face_h, cfg.min_face_size_px)
    item.composition_score = score_composition(w, h, item.face_bbox)
    item.quality_score = calc_quality_score(
        item.face_size_score,
        item.sharpness_score,
        item.exposure_score,
        item.composition_score,
        item.resolution_score,
    )

    if face_w < cfg.min_face_size_px or face_h < cfg.min_face_size_px:
        item.reject_reason = "face_too_small"
    elif item.face_area_ratio < cfg.min_face_ratio:
        item.reject_reason = "face_ratio_too_small"
    elif item.quality_score < cfg.min_quality_score:
        item.reject_reason = "low_quality"

    return item


def analyze_folder(folder: Path, runtime: RuntimeModels, cfg: Config) -> Tuple[List[ImageMetrics], FolderResult]:
    images = list_images(folder)
    result = FolderResult(folder_path=str(folder), scanned=len(images))
    items: List[ImageMetrics] = []

    log(f"[INFO] Analyze folder: {folder} ({len(images)} ảnh)", cfg.verbose)

    for path in images:
        try:
            item = analyze_one_image(path, folder.name, runtime, cfg)
        except Exception as exc:
            item = ImageMetrics(
                path=str(path),
                folder_name=folder.name,
                file_name=path.name,
                reject_reason="analysis_error",
                notes=f"{type(exc).__name__}: {exc}",
            )
        items.append(item)

    result.readable = sum(1 for x in items if x.readable)
    result.no_face = sum(1 for x in items if x.reject_reason == "no_face")
    result.low_quality = sum(
        1 for x in items if x.reject_reason in {"face_too_small", "face_ratio_too_small", "low_quality"}
    )

    usable = [x for x in items if x.face_detected and x.reject_reason == ""]
    compute_clip_embeddings(usable, runtime, cfg)
    result.usable = len(usable)
    return items, result
