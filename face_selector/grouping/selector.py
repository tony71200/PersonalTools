from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from .grouping import apply_duplicate_grouping, build_semantic_pools, select_round_robin_from_pools
from .types import Config, FolderResult, ImageMetrics


def prepare_folder_candidate_pool(items: List[ImageMetrics], cfg: Config, use_faiss: bool) -> List[ImageMetrics]:
    usable = [x for x in items if x.face_detected and x.reject_reason == ""]
    after_dup = apply_duplicate_grouping(usable, cfg)
    semantic_pools = build_semantic_pools(after_dup, cfg, use_faiss)
    total_pool_size = sum(len(p) for p in semantic_pools)
    shortlist_quota = max(1, int(math.ceil(total_pool_size)))
    selected_pool = select_round_robin_from_pools(semantic_pools, shortlist_quota)
    selected_pool.sort(key=lambda x: (x.quality_score, x.face_area_ratio, x.sharpness_score), reverse=True)
    return selected_pool


def redistribute_quotas(capacities: Sequence[int], target: int) -> List[int]:
    caps = list(capacities)
    total_capacity = sum(caps)
    if total_capacity <= 0 or target <= 0:
        return [0] * len(caps)

    target = min(target, total_capacity)
    quotas = [0] * len(caps)
    weights = [c / total_capacity for c in caps]
    raw = [target * w for w in weights]

    for i, val in enumerate(raw):
        quotas[i] = min(caps[i], int(math.floor(val)))

    remain = target - sum(quotas)
    order = sorted(
        range(len(caps)),
        key=lambda i: (raw[i] - quotas[i], caps[i] - quotas[i]),
        reverse=True,
    )

    while remain > 0:
        progressed = False
        for i in order:
            if quotas[i] < caps[i]:
                quotas[i] += 1
                remain -= 1
                progressed = True
                if remain == 0:
                    break
        if not progressed:
            break

    return quotas


def build_final_selection_single(items: List[ImageMetrics], cfg: Config, use_faiss: bool) -> Tuple[List[ImageMetrics], List[ImageMetrics]]:
    pool = prepare_folder_candidate_pool(items, cfg, use_faiss)
    pools = build_semantic_pools(pool, cfg, use_faiss)
    selected = select_round_robin_from_pools(pools, cfg.target_count)
    selected_set = {x.path for x in selected}
    rejected = [x for x in pool if x.path not in selected_set]
    for x in rejected:
        if x.reject_reason == "":
            x.reject_reason = "semantic_overflow"
    return selected, rejected


def build_final_selection_parent(
    all_folder_items: Dict[Path, List[ImageMetrics]],
    folder_results: Dict[Path, FolderResult],
    cfg: Config,
    use_faiss: bool,
) -> Dict[Path, List[ImageMetrics]]:
    candidate_pools: Dict[Path, List[ImageMetrics]] = {}
    capacities: List[int] = []
    folders = list(all_folder_items.keys())

    for folder in folders:
        pool = prepare_folder_candidate_pool(all_folder_items[folder], cfg, use_faiss)
        multiplier = max(1.0, cfg.top_k_folder_shortlist_multiplier)
        shortlist_size = max(1, int(math.ceil(len(pool) / multiplier))) if pool else 0
        if pool and shortlist_size < len(pool):
            pool = pool[:shortlist_size]
        candidate_pools[folder] = pool
        folder_results[folder].final_pool = len(pool)
        capacities.append(len(pool))

    quotas = redistribute_quotas(capacities, cfg.target_count)
    final_map: Dict[Path, List[ImageMetrics]] = {}

    for folder, quota in zip(folders, quotas):
        folder_results[folder].allocated_quota = quota
        pool = candidate_pools[folder]
        semantic_pools = build_semantic_pools(pool, cfg, use_faiss)
        final_map[folder] = select_round_robin_from_pools(semantic_pools, quota)

    return final_map
