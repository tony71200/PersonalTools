from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Set

from .types import Config, FolderResult, ImageMetrics, RuntimeModels
from .utils import ensure_dir, safe_copy_or_move


def mark_selected(items: Iterable[ImageMetrics], selected: Iterable[ImageMetrics]) -> None:
    selected_paths = {x.path for x in selected}
    for item in items:
        item.selected = item.path in selected_paths


def write_outputs_for_folder(
    folder: Path,
    items: List[ImageMetrics],
    selected_paths: Set[str],
    cfg: Config,
) -> FolderResult:
    
    folder_out = cfg.output_path.joinpath(folder.name) if isinstance(cfg.output_path, Path) else Path(cfg.output_path).joinpath(folder.name)
    selected_dir = folder_out.joinpath("selected") if isinstance(folder_out, Path) else Path(folder_out).joinpath("selected")
    no_face_dir = folder_out.joinpath("rejected_no_face") if isinstance(folder_out, Path) else Path(folder_out).joinpath("rejected_no_face")
    low_quality_dir = folder_out.joinpath("rejected_low_quality") if isinstance(folder_out, Path) else Path(folder_out).joinpath("rejected_low_quality")
    duplicate_dir = folder_out.joinpath("rejected_duplicate") if isinstance(folder_out, Path) else Path(folder_out).joinpath("rejected_duplicate")
    overflow_dir = folder_out.joinpath("rejected_overflow") if isinstance(folder_out, Path) else Path(folder_out).joinpath("rejected_overflow")

    for d in (selected_dir, no_face_dir, low_quality_dir, duplicate_dir, overflow_dir):
        ensure_dir(d)

    result = FolderResult(folder_path=str(folder), scanned=len(items))
    result.readable = sum(1 for x in items if x.readable)

    for item in items:
        src = Path(item.path)
        if item.path in selected_paths:
            safe_copy_or_move(src, selected_dir, cfg.copy_files, cfg.dry_run)
            item.selected = True
            result.selected += 1
            continue

        if item.reject_reason == "no_face":
            safe_copy_or_move(src, no_face_dir, cfg.copy_files, cfg.dry_run)
            result.no_face += 1
        elif item.reject_reason in {"face_too_small", "face_ratio_too_small", "low_quality"}:
            safe_copy_or_move(src, low_quality_dir, cfg.copy_files, cfg.dry_run)
            result.low_quality += 1
        elif item.reject_reason == "duplicate":
            safe_copy_or_move(src, duplicate_dir, cfg.copy_files, cfg.dry_run)
            result.duplicate_rejected += 1
        else:
            safe_copy_or_move(src, overflow_dir, cfg.copy_files, cfg.dry_run)

    result.usable = sum(1 for x in items if x.face_detected and x.reject_reason == "")
    return result


def write_report(
    all_items: Dict[Path, List[ImageMetrics]],
    folder_results: Dict[Path, FolderResult],
    cfg: Config,
    runtime: RuntimeModels,
) -> None:
    ensure_dir(cfg.output_path)
    csv_path = cfg.output_path.joinpath("report.csv") if isinstance(cfg.output_path, Path) else Path(cfg.output_path).joinpath("report.csv")
    json_path = cfg.output_path.joinpath("summary.json") if isinstance(cfg.output_path, Path) else Path(cfg.output_path).joinpath("summary.json")

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "path",
                "folder_name",
                "file_name",
                "width",
                "height",
                "readable",
                "face_detected",
                "face_count",
                "face_area_ratio",
                "face_size_score",
                "sharpness_score",
                "exposure_score",
                "composition_score",
                "resolution_score",
                "quality_score",
                "duplicate_group_id",
                "semantic_group_id",
                "selected",
                "reject_reason",
                "notes",
            ],
        )
        writer.writeheader()
        for items in all_items.values():
            for item in items:
                writer.writerow(
                    {
                        "path": item.path,
                        "folder_name": item.folder_name,
                        "file_name": item.file_name,
                        "width": item.width,
                        "height": item.height,
                        "readable": item.readable,
                        "face_detected": item.face_detected,
                        "face_count": item.face_count,
                        "face_area_ratio": round(item.face_area_ratio, 6),
                        "face_size_score": round(item.face_size_score, 6),
                        "sharpness_score": round(item.sharpness_score, 6),
                        "exposure_score": round(item.exposure_score, 6),
                        "composition_score": round(item.composition_score, 6),
                        "resolution_score": round(item.resolution_score, 6),
                        "quality_score": round(item.quality_score, 6),
                        "duplicate_group_id": item.duplicate_group_id,
                        "semantic_group_id": item.semantic_group_id,
                        "selected": item.selected,
                        "reject_reason": item.reject_reason,
                        "notes": item.notes,
                    }
                )

    summary = {
        "mode": cfg.mode,
        "input_path": str(cfg.input_path),
        "output_path": str(cfg.output_path),
        "target_count": cfg.target_count,
        "clip_enabled_runtime": runtime.clip_enabled,
        "faiss_enabled_runtime": runtime.faiss_enabled,
        "folders": {str(folder): asdict(result) for folder, result in folder_results.items()},
        "global": {
            "scanned": sum(r.scanned for r in folder_results.values()),
            "readable": sum(r.readable for r in folder_results.values()),
            "usable": sum(r.usable for r in folder_results.values()),
            "no_face": sum(r.no_face for r in folder_results.values()),
            "low_quality": sum(r.low_quality for r in folder_results.values()),
            "duplicate_rejected": sum(r.duplicate_rejected for r in folder_results.values()),
            "selected": sum(r.selected for r in folder_results.values()),
        },
    }

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
