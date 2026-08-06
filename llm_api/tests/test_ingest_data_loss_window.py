"""run_ingest used to delete the "docs" collection before rebuilding it. An
exception partway through embedding (Ollama down, OOM on a big project) left the
collection gone — the project answered no_answer for everyone until the next
successful ingest. These tests exercise the fix against a real Chroma
PersistentClient rooted at a tmp dir; only get_project and get_embeddings_batch
are mocked (network + DB, not the thing being tested).

Also covers: files with an unsupported extension (e.g. .pdf — no parser exists)
are now reported instead of silently dropped.
"""
from unittest.mock import AsyncMock, patch

import chromadb
import pytest
from chromadb.config import Settings as ChromaSettings

from app.ingest.indexer import get_chroma_path, run_ingest


def _project(project_id: str, sources: list[str]) -> dict:
    return {"project_id": project_id, "sources": sources, "config_json": {}}


def _collection_count(project_id: str) -> int | None:
    """None if the collection does not exist."""
    client = chromadb.PersistentClient(
        path=str(get_chroma_path(project_id)), settings=ChromaSettings(anonymized_telemetry=False)
    )
    try:
        return client.get_collection("docs").count()
    except Exception:
        return None


@pytest.fixture(autouse=True)
def _isolated_chroma_dir(tmp_path):
    with patch("app.config.settings.data_dir", tmp_path):
        yield tmp_path


def _write(dir_path, name: str, text: str):
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / name).write_text(text, encoding="utf-8")


@pytest.mark.asyncio
async def test_successful_ingest_populates_docs_collection(tmp_path):
    src = tmp_path / "src"
    _write(src, "a.md", "Conteúdo sobre bicicletas e passeios.")
    project_id = "p_ok"

    with patch("app.ingest.indexer.get_project", new_callable=AsyncMock, return_value=_project(project_id, [str(src)])), \
        patch("app.ingest.indexer.get_embeddings_batch", new_callable=AsyncMock, return_value=([[0.1, 0.2]], 0)):
        result = await run_ingest(project_id)

    assert result["chunks"] == 1
    assert _collection_count(project_id) == 1


@pytest.mark.asyncio
async def test_failed_embedding_leaves_previous_index_intact(tmp_path):
    """The core regression test: a mid-ingest crash must not empty a live index."""
    src = tmp_path / "src"
    _write(src, "a.md", "Conteúdo original que já está indexado.")
    project_id = "p_fail"

    with patch("app.ingest.indexer.get_project", new_callable=AsyncMock, return_value=_project(project_id, [str(src)])), \
        patch("app.ingest.indexer.get_embeddings_batch", new_callable=AsyncMock, return_value=([[0.1, 0.2]], 0)):
        await run_ingest(project_id)
    assert _collection_count(project_id) == 1

    # Second ingest: source now has more content, but embedding blows up mid-way —
    # simulating Ollama going down partway through a real batch.
    _write(src, "b.md", "Conteúdo novo que nunca vai ser indexado.")
    with patch("app.ingest.indexer.get_project", new_callable=AsyncMock, return_value=_project(project_id, [str(src)])), \
        patch("app.ingest.indexer.get_embeddings_batch", new_callable=AsyncMock, side_effect=ConnectionError("ollama down")):
        with pytest.raises(ConnectionError):
            await run_ingest(project_id)

    # The old, good index must still answer — not "collection not found", not empty.
    assert _collection_count(project_id) == 1


@pytest.mark.asyncio
async def test_emptied_source_still_clears_the_index(tmp_path):
    """Deliberately removing all files must still empty the index (not become stale)."""
    src = tmp_path / "src"
    _write(src, "a.md", "Conteúdo que vai ser removido.")
    project_id = "p_empty"

    with patch("app.ingest.indexer.get_project", new_callable=AsyncMock, return_value=_project(project_id, [str(src)])), \
        patch("app.ingest.indexer.get_embeddings_batch", new_callable=AsyncMock, return_value=([[0.1, 0.2]], 0)):
        await run_ingest(project_id)
    assert _collection_count(project_id) == 1

    (src / "a.md").unlink()
    with patch("app.ingest.indexer.get_project", new_callable=AsyncMock, return_value=_project(project_id, [str(src)])):
        result = await run_ingest(project_id)

    assert result["chunks"] == 0
    assert _collection_count(project_id) == 0


@pytest.mark.asyncio
async def test_unsupported_extension_is_reported_not_silently_dropped():
    src_dir = None
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp)
        _write(src_dir, "note.md", "Texto indexável.")
        _write(src_dir, "fatura.pdf", "%PDF-1.4 fake pdf bytes")
        project_id = "p_pdf"

        with patch("app.ingest.indexer.get_project", new_callable=AsyncMock, return_value=_project(project_id, [str(src_dir)])), \
            patch("app.ingest.indexer.get_embeddings_batch", new_callable=AsyncMock, return_value=([[0.1, 0.2]], 0)):
            result = await run_ingest(project_id)

    assert result["documents"] == 1  # only note.md
    assert result["skipped_files"] == 1
    assert ".pdf" in result["skipped_file_extensions"]


@pytest.mark.asyncio
async def test_no_skipped_files_when_everything_is_supported(tmp_path):
    src = tmp_path / "src"
    _write(src, "a.md", "Só markdown aqui.")
    project_id = "p_clean"

    with patch("app.ingest.indexer.get_project", new_callable=AsyncMock, return_value=_project(project_id, [str(src)])), \
        patch("app.ingest.indexer.get_embeddings_batch", new_callable=AsyncMock, return_value=([[0.1, 0.2]], 0)):
        result = await run_ingest(project_id)

    assert result["skipped_files"] == 0
    assert result["skipped_file_extensions"] == []
