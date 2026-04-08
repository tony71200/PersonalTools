from __future__ import annotations

import shutil
from pathlib import Path
from typing import List
import os

VALID_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def log(msg: str, verbose: bool = True) -> None:
    if verbose:
        print(msg)


def ensure_dir(path: Path) -> None:
    os.makedirs(path, exist_ok=True)


def list_images(folder: Path) -> List[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VALID_EXTS
    )


def safe_copy_or_move(src: Path, dst_dir: Path, copy_files: bool, dry_run: bool) -> Path:
    ensure_dir(dst_dir)
    dst = dst_dir.joinpath(src.name) if isinstance(dst_dir, Path) else Path(dst_dir).joinpath(src.name)
    if dst.exists():
        stem = src.stem
        suffix = src.suffix
        i = 1
        while True:
            candidate = dst_dir.joinpath(f"{stem}_{i}{suffix}") if isinstance(dst_dir, Path) else Path(dst_dir).joinpath(f"{stem}_{i}{suffix}")
            if not candidate.exists():
                dst = candidate
                break
            i += 1
    if not dry_run:
        if copy_files:
            shutil.copy2(src, dst)
        else:
            shutil.move(src, dst)
    return dst


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))
