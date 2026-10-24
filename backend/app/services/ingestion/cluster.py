"""Cluster similar raw items into candidate events."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass

from app.models.raw_news import RawNewsItem
from app.services.ingestion.normalize import title_similarity

SIMILARITY_THRESHOLD = 0.55


@dataclass
class Cluster:
    key: str
    items: list[RawNewsItem]


def assign_clusters(items: list[RawNewsItem], *, threshold: float = SIMILARITY_THRESHOLD) -> list[Cluster]:
    """Greedy clustering by title similarity + shared content_hash."""
    if not items:
        return []

    by_hash: dict[str, list[RawNewsItem]] = defaultdict(list)
    for item in items:
        by_hash[item.content_hash].append(item)

    representatives: list[RawNewsItem] = []
    hash_to_rep: dict[str, RawNewsItem] = {}
    for h, group in by_hash.items():
        rep = group[0]
        representatives.append(rep)
        hash_to_rep[h] = rep

    parent: dict[str, str] = {r.id: r.id for r in representatives}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    reps = list(representatives)
    for i, a in enumerate(reps):
        for b in reps[i + 1 :]:
            if title_similarity(a.title, b.title) >= threshold:
                union(a.id, b.id)

    buckets: dict[str, list[RawNewsItem]] = defaultdict(list)
    for item in items:
        rep = hash_to_rep[item.content_hash]
        root = find(rep.id)
        buckets[root].append(item)

    clusters: list[Cluster] = []
    for root_id, group in buckets.items():
        seed = group[0]
        key_src = "|".join(sorted({i.content_hash[:12] for i in group}))
        key = hashlib.sha1(f"{root_id}|{key_src}".encode("utf-8")).hexdigest()[:24]
        for item in group:
            item.cluster_key = key
        clusters.append(Cluster(key=key, items=group))
    return clusters
