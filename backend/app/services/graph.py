"""Digital Twin path finding — BFS with depth limit, no graph DB required."""

from __future__ import annotations

from collections import deque
from typing import Any

from app.models import CompanyEdge, CompanyNode


def build_adjacency(
    nodes: list[CompanyNode], edges: list[CompanyEdge]
) -> tuple[dict[str, CompanyNode], dict[str, list[tuple[CompanyEdge, str]]]]:
    node_map = {n.id: n for n in nodes}
    adj: dict[str, list[tuple[CompanyEdge, str]]] = {n.id: [] for n in nodes}
    for edge in edges:
        if edge.from_node_id in adj and edge.to_node_id in node_map:
            adj[edge.from_node_id].append((edge, edge.to_node_id))
        if edge.to_node_id in adj and edge.from_node_id in node_map:
            # undirected walk for impact discovery in MVP
            adj[edge.to_node_id].append((edge, edge.from_node_id))
    return node_map, adj


def find_paths(
    start_ids: set[str],
    nodes: list[CompanyNode],
    edges: list[CompanyEdge],
    *,
    max_depth: int = 5,
    stop_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return shortest explainable paths from matched entry nodes to exposure nodes."""
    stop_types = stop_types or {"production_line", "product", "facility"}
    node_map, adj = build_adjacency(nodes, edges)
    results: list[dict[str, Any]] = []
    seen_terminals: set[str] = set()

    for start in start_ids:
        if start not in node_map:
            continue
        queue: deque[tuple[str, list[str], list[str], set[str]]] = deque(
            [(start, [start], [], {start})]
        )
        while queue:
            current, node_path, edge_path, visited = queue.popleft()
            current_node = node_map[current]
            if len(node_path) > 1 and current_node.node_type in stop_types:
                if current not in seen_terminals:
                    seen_terminals.add(current)
                    results.append(
                        {
                            "nodes": [
                                {
                                    "id": nid,
                                    "name": node_map[nid].name,
                                    "node_type": node_map[nid].node_type,
                                    "output_share_percent": node_map[nid].output_share_percent,
                                    "country": node_map[nid].country,
                                }
                                for nid in node_path
                            ],
                            "edge_ids": edge_path,
                            "terminal_id": current,
                            "exposure_value": current_node.output_share_percent,
                        }
                    )
                continue
            if len(node_path) >= max_depth:
                continue
            for edge, nxt in adj.get(current, []):
                if nxt in visited:
                    continue
                queue.append((nxt, node_path + [nxt], edge_path + [edge.id], visited | {nxt}))

    # Prefer known exposure (incl. 0.0) over unknown (None); then higher share.
    # Do not treat missing share as zero for ranking — that hid real 0% paths.
    def _path_sort_key(p: dict[str, Any]) -> tuple[int, float]:
        raw = p.get("exposure_value")
        if raw is None:
            return (1, 0.0)
        return (0, -float(raw))

    results.sort(key=_path_sort_key)
    return results


def match_event_to_nodes(event_countries: list[str], nodes: list[CompanyNode]) -> set[str]:
    """Match entry nodes by country with alias expansion (China ↔ Китай)."""
    from app.services.relevance import expand_country_tokens

    countries = expand_country_tokens(event_countries)
    matched: set[str] = set()
    for node in nodes:
        node_tokens: set[str] = set()
        if node.country:
            node_tokens |= expand_country_tokens([node.country])
        node_tokens |= expand_country_tokens([node.name])
        attrs = node.attributes_json or {}
        node_tokens |= expand_country_tokens(attrs.get("countries") or [])
        if countries & node_tokens:
            # Prefer supplier/market geography nodes as path starts
            if node.node_type in {"supplier", "market", "facility"}:
                matched.add(node.id)
            elif node.country:
                matched.add(node.id)
    return matched
