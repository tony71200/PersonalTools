from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Sequence

import numpy as np

from .quality import hamming_distance
from .types import Config, ImageMetrics


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def group_by_near_duplicate(items: Sequence[ImageMetrics], threshold: int) -> Dict[int, List[int]]:
    n = len(items)
    uf = UnionFind(n)
    hashes = [x.dhash for x in items]

    for i in range(n):
        if hashes[i] is None:
            continue
        for j in range(i + 1, n):
            if hashes[j] is None:
                continue
            if hamming_distance(int(hashes[i]), int(hashes[j])) <= threshold:
                uf.union(i, j)

    groups: Dict[int, List[int]] = defaultdict(list)
    for idx in range(n):
        groups[uf.find(idx)].append(idx)
    return groups


def apply_duplicate_grouping(items: List[ImageMetrics], cfg: Config) -> List[ImageMetrics]:
    if not items:
        return []

    groups = group_by_near_duplicate(items, cfg.duplicate_hash_threshold)
    survivors: List[ImageMetrics] = []

    for gid, idxs in enumerate(groups.values()):
        group_items = [items[i] for i in idxs]
        group_items.sort(key=lambda x: (x.quality_score, x.face_area_ratio, x.sharpness_score), reverse=True)
        for rank, item in enumerate(group_items):
            item.duplicate_group_id = gid
            if rank < cfg.top_k_per_duplicate_group:
                survivors.append(item)
            else:
                item.reject_reason = "duplicate"
    return survivors


def _group_by_semantic_similarity_naive(items: List[ImageMetrics], threshold: float) -> Dict[int, List[int]]:
    n = len(items)
    uf = UnionFind(n)
    embs = [x.clip_embedding for x in items]

    for i in range(n):
        if embs[i] is None:
            continue
        for j in range(i + 1, n):
            if embs[j] is None:
                continue
            if cosine_similarity(embs[i], embs[j]) >= threshold:
                uf.union(i, j)

    groups: Dict[int, List[int]] = defaultdict(list)
    for idx in range(n):
        groups[uf.find(idx)].append(idx)
    return groups


def _group_by_semantic_similarity_faiss(items: List[ImageMetrics], threshold: float) -> Dict[int, List[int]]:
    import faiss

    valid = [(i, x.clip_embedding) for i, x in enumerate(items) if x.clip_embedding is not None]
    if not valid:
        return {i: [i] for i in range(len(items))}

    indices = [i for i, _ in valid]
    embs = np.asarray([emb for _, emb in valid], dtype="float32")
    faiss.normalize_L2(embs)

    index = faiss.IndexFlatIP(embs.shape[1])
    index.add(embs)

    lims, D, I = index.range_search(embs, threshold)

    uf = UnionFind(len(items))
    for row in range(len(indices)):
        start = lims[row]
        end = lims[row + 1]
        src_idx = indices[row]
        for pos in range(start, end):
            dst_local = int(I[pos])
            dst_idx = indices[dst_local]
            if src_idx != dst_idx:
                uf.union(src_idx, dst_idx)

    groups: Dict[int, List[int]] = defaultdict(list)
    for idx in range(len(items)):
        groups[uf.find(idx)].append(idx)
    return groups


def group_by_semantic_similarity(items: List[ImageMetrics], threshold: float, use_faiss: bool) -> Dict[int, List[int]]:
    if use_faiss:
        try:
            return _group_by_semantic_similarity_faiss(items, threshold)
        except Exception:
            return _group_by_semantic_similarity_naive(items, threshold)
    return _group_by_semantic_similarity_naive(items, threshold)


def build_semantic_pools(items: List[ImageMetrics], cfg: Config, use_faiss: bool) -> List[Deque[ImageMetrics]]:
    if not items:
        return []

    if all(x.clip_embedding is None for x in items):
        pools: List[Deque[ImageMetrics]] = []
        for gid, item in enumerate(sorted(items, key=lambda x: x.quality_score, reverse=True)):
            item.semantic_group_id = gid
            pools.append(deque([item]))
        return pools

    groups = group_by_semantic_similarity(items, cfg.semantic_similarity_threshold, use_faiss)
    pools = []

    for gid, idxs in enumerate(groups.values()):
        group_items = [items[i] for i in idxs]
        group_items.sort(key=lambda x: (x.quality_score, x.face_area_ratio, x.sharpness_score), reverse=True)
        limited = group_items[: cfg.top_k_per_semantic_group]
        for item in limited:
            item.semantic_group_id = gid
        pools.append(deque(limited))

    pools.sort(key=lambda dq: dq[0].quality_score if dq else 0.0, reverse=True)
    return pools


def select_round_robin_from_pools(pools: List[Deque[ImageMetrics]], quota: int) -> List[ImageMetrics]:
    if quota <= 0:
        return []

    selected: List[ImageMetrics] = []
    active = deque([dq for dq in pools if dq])

    while active and len(selected) < quota:
        current = active.popleft()
        if current:
            selected.append(current.popleft())
        if current and len(selected) < quota:
            active.append(current)
    return selected
