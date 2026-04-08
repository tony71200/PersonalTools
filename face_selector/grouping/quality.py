from __future__ import annotations

import math

import cv2
import numpy as np

from .utils import clamp01


def score_face_size(face_area_ratio: float, face_w: float, face_h: float, min_face_px: int) -> float:
    if face_w < min_face_px or face_h < min_face_px:
        return 0.0
    target = 0.18
    return clamp01(min(face_area_ratio / target, 1.0))


def score_sharpness(gray: np.ndarray) -> float:
    val = cv2.Laplacian(gray, cv2.CV_64F).var()
    return clamp01((val - 40.0) / 260.0)


def score_exposure(gray: np.ndarray) -> float:
    mean = float(np.mean(gray))
    std = float(np.std(gray))
    mean_score = 1.0 - min(abs(mean - 145.0) / 110.0, 1.0)
    contrast_score = clamp01((std - 25.0) / 60.0)
    return clamp01(0.7 * mean_score + 0.3 * contrast_score)


def score_composition(img_w: int, img_h: int, bbox: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = bbox
    face_cx = (x1 + x2) / 2.0
    face_cy = (y1 + y2) / 2.0
    img_cx = img_w / 2.0
    img_cy = img_h / 2.0
    dx = abs(face_cx - img_cx) / max(img_w / 2.0, 1.0)
    dy = abs(face_cy - img_cy) / max(img_h / 2.0, 1.0)
    center_score = 1.0 - min(math.sqrt(dx * dx + dy * dy), 1.0)
    margin = min(x1, y1, img_w - x2, img_h - y2)
    face_min_side = max(min(x2 - x1, y2 - y1), 1.0)
    crop_penalty = clamp01(margin / (0.12 * face_min_side))
    return clamp01(0.65 * center_score + 0.35 * crop_penalty)


def score_resolution(img_w: int, img_h: int) -> float:
    mp = (img_w * img_h) / 1_000_000.0
    return clamp01(mp / 1.6)


def calc_quality_score(
    face_size_score: float,
    sharpness_score: float,
    exposure_score: float,
    composition_score: float,
    resolution_score: float,
) -> float:
    score = (
        0.30 * face_size_score
        + 0.25 * sharpness_score
        + 0.15 * exposure_score
        + 0.15 * composition_score
        + 0.15 * resolution_score
    )
    return clamp01(score)


def dhash_from_gray(gray: np.ndarray, hash_size: int = 8) -> int:
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = 0
    for bit in diff.flatten():
        bits = (bits << 1) | int(bit)
    return bits


def hamming_distance(a: int, b: int) -> int:
    return int((a ^ b).bit_count())
