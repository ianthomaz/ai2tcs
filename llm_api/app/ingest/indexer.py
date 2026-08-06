"""Build/update vector index per project (Chroma on disk)."""
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.ingest.chunking import iter_files, split_text
from app.ingest.embeddings import get_embeddings_batch
from app.registry import get_chunking_config, get_project

logger = logging.getLogger(__name__)

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

    `incremental` is accepted for API compatibility but not read: every call is a
    full rebuild (all sources re-chunked and re-embedded). There is no per-file
    hash/mtime tracking to support a real incremental path yet.
    """
    project = await get_project(project_id)
    if not project:
        return {"error": "project not found", "documents": 0, "chunks": 0}
    sources = project.get("sources") or []
    if not sources:
        return {"error": "no sources configured", "documents": 0, "chunks": 0}

    chunking = get_chunking_config(project)
    embed_model = "mxbai-embed-large"
    if isinstance(project.get("config_json"), dict):
        embed_model = (project["config_json"] or {}).get("embedding_model") or embed_model

    path = get_chroma_path(project_id)
    path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection_name = "docs"

    files_skipped: list[tuple[Path, str]] = []
    files = iter_files(sources, skipped_out=files_skipped)
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

    unsupported_ext = sorted({f.suffix.lower() or "(sem extensão)" for f, reason in files_skipped if reason == "unsupported_extension"})
    if files_skipped:
        logger.warning(
            "Ingest project_id=%s skipped %d file(s) not indexed: extensions=%s (parsers exist only for .txt/.md/.markdown/.rst/.json)",
            project_id,
            len(files_skipped),
            unsupported_ext or "n/a",
        )

    # Build into a staging collection and only replace "docs" on success. Deleting
    # "docs" up front (the previous behaviour, for every ingest including an empty
    # corpus) meant an exception partway through embedding/add — Ollama down, OOM on
    # a big project — left the collection gone and the project answering no_answer
    # for everyone until the next successful ingest. A failed run now leaves the
    # previous index exactly as it was. An empty corpus (sources legitimately have
    # nothing left) still swaps in, same as before — it just can't fail mid-swap the
    # way a real embedding batch over the network can.
    staging_name = f"{collection_name}__staging"
    try:
        client.delete_collection(staging_name)
    except Exception:
        pass
    staging = client.create_collection(
        staging_name,
        # Cosine distance so retrieve distances are in [0, 2]; worker filters with
        # configurable max_chunk_distance (default 1.0).
        metadata={"description": project_id, "hnsw:space": "cosine"},
    )

    skipped = 0
    if all_chunks:
        texts = [c[1] for c in all_chunks]
        ids = [c[0] for c in all_chunks]
        # path = internal file path (not exposed to end user). url = optional external
        # link (exposed in API when present). title/section = extracted from chunk
        # content for richer retrieval metadata (março 2026).
        metadatas = [_extract_chunk_metadata(c[1], c[2]) for c in all_chunks]
        try:
            embeddings, skipped = await get_embeddings_batch(texts, model=embed_model)
            staging.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        except Exception:
            try:
                client.delete_collection(staging_name)
            except Exception:
                pass
            raise

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    staging.modify(name=collection_name)

    if not all_chunks:
        return {
            "documents": document_count,
            "chunks": 0,
            "skipped_files": len(files_skipped),
            "skipped_file_extensions": unsupported_ext,
        }

    indexed = len(all_chunks) - skipped
    result = {
        "project_id": project_id,
        "documents": document_count,
        "chunks": len(all_chunks),
        "indexed": indexed,
        "skipped": skipped,
        "skipped_files": len(files_skipped),
        "skipped_file_extensions": unsupported_ext,
    }
    logger.info(
        "Ingest complete project_id=%s indexed=%s skipped=%s documents=%s chunks=%s",
        project_id,
        indexed,
        skipped,
        document_count,
        len(all_chunks),
    )
    # Persist last ingest result for dashboard (indexation status)
    last_ingest_path = path / "last_ingest.json"
    try:
        last_ingest_path.write_text(
            json.dumps(
                {
                    "documents": result["documents"],
                    "chunks": result["chunks"],
                    "indexed": result["indexed"],
                    "skipped": result["skipped"],
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
