"""Build/update vector index per project (Chroma on disk)."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.ingest.chunking import iter_files, split_text
from app.ingest.embeddings import get_embeddings_batch
from app.registry import get_chunking_config, get_project

# Regex to extract heading from chunk text (março 2026 — enriched metadata for retrieval)
_HEADING_RE = re.compile(r"^#{1,4}\s+(.+)", re.MULTILINE)
_SOBRE_RE = re.compile(r"^Sobre:\s*(.+?)(?:\.\s*Palavras-chave:|$)", re.MULTILINE)


def _extract_chunk_metadata(chunk_text: str, file_path: str) -> dict:
    """Extract structured metadata from a chunk for richer Chroma storage.

    Added março 2026: title and section metadata improve future retrieval filtering
    and help understand what each chunk covers without reading the full text.
    """
    meta: dict = {"path": file_path}
    # Try to extract title from "Sobre: ..." line (added by normalize_markdown)
    sobre = _SOBRE_RE.search(chunk_text)
    if sobre:
        meta["title"] = sobre.group(1).strip()[:200]
    # Extract section heading if present
    heading = _HEADING_RE.search(chunk_text)
    if heading:
        meta["section"] = heading.group(1).strip()[:200]
    return meta


def get_chroma_path(project_id: str) -> Path:
    return settings.data_dir / project_id / "chroma"


async def run_ingest(project_id: str, incremental: bool = True) -> dict:
    """
    Ingest project sources into Chroma. Creates or overwrites collection for project_id.
    Returns { "documents": N, "chunks": M }.
    """
    project = await get_project(project_id)
    if not project:
        return {"error": "project not found", "documents": 0, "chunks": 0}
    sources = project.get("sources") or []
    if not sources:
        return {"error": "no sources configured", "documents": 0, "chunks": 0}

    chunking = get_chunking_config(project)
    embed_model = "nomic-embed-text"
    if isinstance(project.get("config_json"), dict):
        embed_model = (project["config_json"] or {}).get("embedding_model") or embed_model

    path = get_chroma_path(project_id)
    path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection_name = "docs"
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    # Use cosine distance so retrieve distances are in [0, 2]; worker filters with configurable max_chunk_distance (default 1.0)
    collection = client.create_collection(
        collection_name,
        metadata={"description": project_id, "hnsw:space": "cosine"},
    )

    files = iter_files(sources)
    all_chunks: list[tuple[str, str, str]] = []  # (id, text, path)
    document_count = 0
    for fpath, text in files:
        document_count += 1
        chunks = split_text(
            text,
            chunk_size=chunking["chunk_size"],
            chunk_overlap=chunking["chunk_overlap"],
            separator=chunking["separator"],
        )
        path_hash = hashlib.md5(str(fpath).encode()).hexdigest()[:12]
        for i, c in enumerate(chunks):
            doc_id = f"{path_hash}_{i}"
            all_chunks.append((doc_id, c, str(fpath)))

    if not all_chunks:
        return {"documents": document_count, "chunks": 0}

    texts = [c[1] for c in all_chunks]
    ids = [c[0] for c in all_chunks]
    # path = internal file path (not exposed to end user). url = optional external link (exposed in API when present).
    # title/section = extracted from chunk content for richer retrieval metadata (março 2026).
    metadatas = [_extract_chunk_metadata(c[1], c[2]) for c in all_chunks]

    embeddings = await get_embeddings_batch(texts, model=embed_model)
    collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    result = {"documents": document_count, "chunks": len(all_chunks)}
    # Persist last ingest result for dashboard (indexation status)
    last_ingest_path = path / "last_ingest.json"
    try:
        last_ingest_path.write_text(
            json.dumps(
                {
                    "documents": result["documents"],
                    "chunks": result["chunks"],
                    "at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return result


def get_index_stats(project_id: str) -> dict:
    """
    Return indexation stats for a project: chunks in Chroma and last ingest result if any.
    Used by dashboard to show "indexação" per library.
    """
    path = get_chroma_path(project_id)
    stats: dict = {"chunks": 0, "last_ingest": None}
    if not path.exists():
        return stats
    try:
        client = chromadb.PersistentClient(
            path=str(path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        coll = client.get_collection("docs")
        stats["chunks"] = coll.count()
    except Exception:
        pass
    last_ingest_file = path / "last_ingest.json"
    if last_ingest_file.exists():
        try:
            data = json.loads(last_ingest_file.read_text(encoding="utf-8"))
            stats["last_ingest"] = {
                "documents": data.get("documents", 0),
                "chunks": data.get("chunks", 0),
                "at": data.get("at"),
            }
        except Exception:
            pass
    return stats
