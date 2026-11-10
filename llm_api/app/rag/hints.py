"""Retrieval hints: a project tells the search which of its files matter more for a channel.

Shape (config_json.retrieval_hints, same as a client contract file such as
contracts/bikeanjo/rag/retrieval-hints.json):

    {"ports": {"ask": {"boost_path_substrings": [...], "downrank_path_substrings": [...],
                       "exclude_path_substrings": [...]}},
     "intent_clusters": {"<name>": {"keywords": [...], "boost_path_substrings": [...],
                                    "extra_downrank": [...]}}}

Hints only reorder (and exclude): the distance threshold still reads the raw distance, so a
boost never lets a far passage in. docs/08-project-config.md § retrieval_hints.
"""
from __future__ import annotations

from typing import Any

from app.llm.signals import fold

BOOST = 0.05
DOWNRANK = 0.08
CLUSTER_BOOST = 0.08


def project_hints(project: dict | None, port: str) -> dict[str, Any] | None:
    """{"port": {...}, "intent_clusters": {...}} for this port, or None when the project has none."""
    cfg = (project or {}).get("config_json")
    raw = cfg.get("retrieval_hints") if isinstance(cfg, dict) else None
    if not isinstance(raw, dict):
        return None
    port_hints = (raw.get("ports") or {}).get(port)
    clusters = raw.get("intent_clusters")
    if not isinstance(port_hints, dict) and not isinstance(clusters, dict):
        return None
    return {
        "port": port_hints if isinstance(port_hints, dict) else {},
        "intent_clusters": clusters if isinstance(clusters, dict) else {},
    }


def matched_clusters(query: str, clusters: dict[str, Any]) -> list[dict[str, Any]]:
    q = fold(query or "")
    out = []
    for c in clusters.values():
        if isinstance(c, dict) and any(fold(k) in q for k in c.get("keywords") or [] if isinstance(k, str) and k.strip()):
            out.append(c)
    return out


def _strs(v: Any) -> list[str]:
    return [s for s in v if isinstance(s, str) and s] if isinstance(v, list) else []


def apply(chunks: list[dict], hints: dict[str, Any] | None, query: str = "") -> list[dict]:
    """Chunks reordered by adjusted distance (raw distance ± boosts), excluded paths removed.

    Each chunk gains `adjusted_distance`; `distance` stays the raw one.
    """
    if not hints:
        return chunks
    port = hints.get("port") or {}
    boost, down, exclude = (_strs(port.get(k)) for k in ("boost_path_substrings", "downrank_path_substrings", "exclude_path_substrings"))
    clusters = matched_clusters(query, hints.get("intent_clusters") or {}) if query else []
    cluster_boost = [s for c in clusters for s in _strs(c.get("boost_path_substrings"))]
    cluster_down = [s for c in clusters for s in _strs(c.get("extra_downrank"))]
    out = []
    for c in chunks:
        path = c.get("path") or ""
        if any(s in path for s in exclude):
            continue
        # Base: the hybrid keyword score when it ran, else the raw distance.
        d = c.get("_hybrid_score", c.get("distance"))
        adj = float(d) if d is not None else 2.0
        in_cluster = any(s in path for s in cluster_boost)
        if in_cluster:
            adj -= CLUSTER_BOOST
        elif any(s in path for s in boost):
            adj -= BOOST
        # A cluster that asks for a file lifts its general downrank (e.g. «estatuto» asks for it).
        if any(s in path for s in down) and not in_cluster:
            adj += DOWNRANK
        if any(s in path for s in cluster_down):
            adj += DOWNRANK
        out.append({**c, "adjusted_distance": round(adj, 4)})
    out.sort(key=lambda c: c["adjusted_distance"])
    return out
