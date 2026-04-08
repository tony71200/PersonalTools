from __future__ import annotations

import argparse
from pathlib import Path

from .analyzer import analyze_folder
from .models import load_models
from .reporting import mark_selected, write_outputs_for_folder, write_report
from .selector import build_final_selection_parent, build_final_selection_single
from .types import Config
from .utils import ensure_dir, list_images, log


def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        description="Face photo selector with InsightFace + optional CLIP + optional FAISS."
    )
    parser.add_argument("--mode", choices=["single", "parent"], required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--move", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-clip", action="store_true")
    parser.add_argument("--disable-faiss", action="store_true")
    parser.add_argument("--recursive-parent", action="store_true")
    parser.add_argument("--clip-model-name", default="openai/clip-vit-base-patch32")
    parser.add_argument("--clip-batch-size", type=int, default=8)
    parser.add_argument("--clip-cache-dir", default=None)
    parser.add_argument("--det-model-name", default="buffalo_l")
    parser.add_argument("--det-size", type=int, nargs=2, default=[640, 640])
    parser.add_argument("--min-face-size-px", type=int, default=48)
    parser.add_argument("--min-face-ratio", type=float, default=0.03)
    parser.add_argument("--min-quality-score", type=float, default=0.35)
    parser.add_argument("--duplicate-hash-threshold", type=int, default=6)
    parser.add_argument("--semantic-similarity-threshold", type=float, default=0.92)
    parser.add_argument("--top-k-per-duplicate-group", type=int, default=1)
    parser.add_argument("--top-k-per-semantic-group", type=int, default=3)
    parser.add_argument("--top-k-folder-shortlist-multiplier", type=float, default=2.0)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_path.exists() or not input_path.is_dir():
        raise SystemExit(f"Input không hợp lệ: {input_path}")
    if args.target < 0:
        raise SystemExit("--target phải >= 0")

    return Config(
        mode=args.mode,
        input_path=input_path,
        output_path=output_path,
        target_count=args.target,
        recursive_parent=args.recursive_parent,
        copy_files=not args.move,
        dry_run=args.dry_run,
        enable_clip=not args.disable_clip,
        enable_faiss=not args.disable_faiss,
        clip_model_name=args.clip_model_name,
        clip_batch_size=args.clip_batch_size,
        clip_cache_dir=args.clip_cache_dir,
        det_model_name=args.det_model_name,
        det_size=(args.det_size[0], args.det_size[1]),
        min_face_size_px=args.min_face_size_px,
        min_face_ratio=args.min_face_ratio,
        min_quality_score=args.min_quality_score,
        duplicate_hash_threshold=args.duplicate_hash_threshold,
        semantic_similarity_threshold=args.semantic_similarity_threshold,
        top_k_per_duplicate_group=args.top_k_per_duplicate_group,
        top_k_per_semantic_group=args.top_k_per_semantic_group,
        top_k_folder_shortlist_multiplier=args.top_k_folder_shortlist_multiplier,
        verbose=not args.quiet,
    )


def collect_folders(cfg: Config):
    if cfg.mode == "single":
        return [Path(cfg.input_path)] if list_images(Path(cfg.input_path)) else []
    if cfg.recursive_parent:
        return sorted([p for p in Path(cfg.input_path).rglob("*") if Path(p).is_dir() and list_images(Path(p))])
    return sorted([p for p in Path(cfg.input_path).iterdir() if Path(p).is_dir()])


def run() -> None:
    cfg = parse_args()
    ensure_dir(cfg.output_path)

    folders = collect_folders(cfg)
    if not folders:
        raise SystemExit("Không tìm thấy folder ảnh phù hợp.")

    log(f"[INFO] Mode: {cfg.mode}", cfg.verbose)
    log(f"[INFO] Folders: {len(folders)}", cfg.verbose)
    log(f"[INFO] Target: {cfg.target_count}", cfg.verbose)

    runtime = load_models(cfg)

    all_items = {}
    folder_results = {}

    for folder in folders:
        items, result = analyze_folder(folder, runtime, cfg)
        all_items[folder] = items
        folder_results[folder] = result

    final_selected_map = {}

    if cfg.mode == "single":
        folder = folders[0]
        selected, _ = build_final_selection_single(all_items[folder], cfg, runtime.faiss_enabled)
        selected_paths = {x.path for x in selected}
        for item in all_items[folder]:
            if item.path not in selected_paths and item.reject_reason == "":
                item.reject_reason = "semantic_overflow"
        final_selected_map[folder] = selected
    else:
        final_selected_map = build_final_selection_parent(all_items, folder_results, cfg, runtime.faiss_enabled)
        all_selected_paths = {x.path for lst in final_selected_map.values() for x in lst}
        for folder, items in all_items.items():
            for item in items:
                if item.path not in all_selected_paths and item.reject_reason == "":
                    item.reject_reason = "semantic_overflow"

    output_results = {}
    for folder in folders:
        selected_paths = {x.path for x in final_selected_map.get(folder, [])}
        result = write_outputs_for_folder(folder, all_items[folder], selected_paths, cfg)
        if folder in folder_results:
            result.allocated_quota = folder_results[folder].allocated_quota
            result.final_pool = folder_results[folder].final_pool
        output_results[folder] = result

    for folder, items in all_items.items():
        mark_selected(items, final_selected_map.get(folder, []))

    write_report(all_items, output_results, cfg, runtime)

    global_selected = sum(r.selected for r in output_results.values())
    global_scanned = sum(r.scanned for r in output_results.values())
    global_usable = sum(r.usable for r in output_results.values())

    log(f"[DONE] scanned={global_scanned} usable={global_usable} selected={global_selected}", cfg.verbose)
    log(f"[DONE] report={cfg.output_path / 'report.csv'}", cfg.verbose)
    log(f"[DONE] summary={cfg.output_path / 'summary.json'}", cfg.verbose)

def run_test(cfg: Config) -> None:
    cfg = cfg or parse_args()
    ensure_dir(cfg.output_path)

    folders = collect_folders(cfg)
    if not folders:
        raise SystemExit("Không tìm thấy folder ảnh phù hợp.")

    log(f"[INFO] Mode: {cfg.mode}", cfg.verbose)
    log(f"[INFO] Folders: {len(folders)}", cfg.verbose)
    log(f"[INFO] Target: {cfg.target_count}", cfg.verbose)

    runtime = load_models(cfg)

    all_items = {}
    folder_results = {}

    for folder in folders:
        items, result = analyze_folder(folder, runtime, cfg)
        all_items[folder] = items
        folder_results[folder] = result

    final_selected_map = {}

    if cfg.mode == "single":
        folder = folders[0]
        selected, _ = build_final_selection_single(all_items[folder], cfg, runtime.faiss_enabled)
        selected_paths = {x.path for x in selected}
        for item in all_items[folder]:
            if item.path not in selected_paths and item.reject_reason == "":
                item.reject_reason = "semantic_overflow"
        final_selected_map[folder] = selected
    else:
        final_selected_map = build_final_selection_parent(all_items, folder_results, cfg, runtime.faiss_enabled)
        all_selected_paths = {x.path for lst in final_selected_map.values() for x in lst}
        for folder, items in all_items.items():
            for item in items:
                if item.path not in all_selected_paths and item.reject_reason == "":
                    item.reject_reason = "semantic_overflow"

    output_results = {}
    for folder in folders:
        selected_paths = {x.path for x in final_selected_map.get(folder, [])}
        result = write_outputs_for_folder(folder, all_items[folder], selected_paths, cfg)
        if folder in folder_results:
            result.allocated_quota = folder_results[folder].allocated_quota
            result.final_pool = folder_results[folder].final_pool
        output_results[folder] = result

    for folder, items in all_items.items():
        mark_selected(items, final_selected_map.get(folder, []))

    write_report(all_items, output_results, cfg, runtime)

    global_selected = sum(r.selected for r in output_results.values())
    global_scanned = sum(r.scanned for r in output_results.values())
    global_usable = sum(r.usable for r in output_results.values())

    log(f"[DONE] scanned={global_scanned} usable={global_usable} selected={global_selected}", cfg.verbose)
    log(f"[DONE] report={cfg.output_path.joinpath('report.csv') if isinstance(cfg.output_path, Path) else Path(cfg.output_path).joinpath('report.csv')}", cfg.verbose)
    log(f"[DONE] summary={cfg.output_path.joinpath('summary.json') if isinstance(cfg.output_path, Path) else Path(cfg.output_path).joinpath('summary.json')}", cfg.verbose)
