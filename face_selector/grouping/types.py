from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


@dataclass
class Config:
    mode: str
    input_path: Path
    output_path: Path
    target_count: int
    recursive_parent: bool = False
    copy_files: bool = True
    dry_run: bool = False
    enable_clip: bool = True
    enable_faiss: bool = True
    clip_model_name: str = "openai/clip-vit-base-patch32"
    clip_batch_size: int = 8
    clip_cache_dir: Optional[str] = None
    det_model_name: str = "buffalo_l"
    det_size: Tuple[int, int] = (640, 640)
    min_face_size_px: int = 48
    min_face_ratio: float = 0.03
    min_quality_score: float = 0.35
    duplicate_hash_threshold: int = 6
    semantic_similarity_threshold: float = 0.92
    top_k_per_duplicate_group: int = 1
    top_k_per_semantic_group: int = 3
    top_k_folder_shortlist_multiplier: float = 2.0
    verbose: bool = True


@dataclass
class ImageMetrics:
    path: str
    folder_name: str
    file_name: str
    width: int = 0
    height: int = 0
    readable: bool = False
    face_detected: bool = False
    face_count: int = 0
    face_bbox: Optional[Tuple[float, float, float, float]] = None
    face_area_ratio: float = 0.0
    face_size_score: float = 0.0
    sharpness_score: float = 0.0
    exposure_score: float = 0.0
    composition_score: float = 0.0
    resolution_score: float = 0.0
    quality_score: float = 0.0
    dhash: Optional[int] = None
    clip_embedding: Optional[np.ndarray] = None
    semantic_group_id: Optional[int] = None
    duplicate_group_id: Optional[int] = None
    selected: bool = False
    reject_reason: str = ""
    notes: str = ""


@dataclass
class FolderResult:
    folder_path: str
    scanned: int = 0
    readable: int = 0
    usable: int = 0
    no_face: int = 0
    low_quality: int = 0
    duplicate_rejected: int = 0
    selected: int = 0
    allocated_quota: int = 0
    final_pool: int = 0


@dataclass
class RuntimeModels:
    det_model: object
    clip_model: Optional[object] = None
    clip_processor: Optional[object] = None
    clip_device: str = "cpu"
    clip_enabled: bool = False
    faiss_enabled: bool = False
