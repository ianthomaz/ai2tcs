"""Retrieve relevant chunks from project Chroma index."""
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.ingest.embeddings import get_embedding_async


def get_chroma_path(project_id: str) -> Path:
    return settings.data_dir / project_id / "chroma"


def get_shared_chroma_path(library_slug: str) -> Path:
    return settings.data_dir / "_shared" / library_slug / "chroma"


async def _retrieve_from_path(
    path: Path,
    query_embedding: list[float],
    top_k: int = 5,
    origin: str = "project"
) -> list[dict]:
    if not path.exists():
        return []
    client = chromadb.PersistentClient(
        path=str(path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    try:
        collection = client.get_collection("docs")
    except Exception:
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, 20),
        include=["documents", "metadatas", "distances"],
    )
    if not results or not results["ids"] or not results["ids"][0]:
        return []
    out = []
    for i, doc_id in enumerate(results["ids"][0]):
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results["metadatas"] and results["metadatas"][0] else []
        dists = results["distances"][0] if results.get("distances") and results["distances"][0] else []
        meta = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else None
        snippet = docs[i] if i < len(docs) else ""
        out.append({
            "id": doc_id,
            "path": meta.get("path", ""),
            "snippet": snippet,
            "distance": dist,
            "url": meta.get("url") or None,
            "origin": origin,
        })
    return out


async def retrieve(
    project_id: str,
    query: str,
    top_k: int = 5,
    embedding_model: str = "nomic-embed-text",
) -> list[dict]:
    """
    Return list of { "id", "path", "snippet", "distance", "origin" } for top_k chunks.
    Retrieves from project index AND shared libraries if configured.
    """
    from app.registry import get_project
    project = await get_project(project_id)
    shared_libraries = []
    if project and project.get("config_json"):
        shared_libraries = project["config_json"].get("shared_libraries", [])

    query_embedding = await get_embedding_async(query, model=embedding_model)

    # 1. Retrieve from project
    tasks = [
        _retrieve_from_path(get_chroma_path(project_id), query_embedding, top_k=top_k, origin="project")
    ]

    # 2. Retrieve from shared libraries
    for slug in shared_libraries:
        tasks.append(
            _retrieve_from_path(get_shared_chroma_path(slug), query_embedding, top_k=top_k, origin=f"shared:{slug}")
        )

    all_results = await asyncio.gather(*tasks)

    # Flatten and sort
    merged = [item for sublist in all_results for item in sublist]
    merged.sort(key=lambda x: x["distance"] if x["distance"] is not None else 2.0)

    return merged[:top_k]
