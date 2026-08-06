"""iter_files had zero test coverage. skipped_out is what closes the "PDF/DOCX
silently dropped" gap in the ingest pipeline — tested directly here, cheaper than
going through the full run_ingest + Chroma path in test_ingest_data_loss_window.py.
"""
from pathlib import Path

from app.ingest.chunking import iter_files


def test_supported_files_are_returned_and_nothing_is_reported_skipped(tmp_path):
    (tmp_path / "a.md").write_text("conteúdo", encoding="utf-8")
    (tmp_path / "b.txt").write_text("conteúdo", encoding="utf-8")
    skipped: list[tuple[Path, str]] = []

    files = iter_files([str(tmp_path)], skipped_out=skipped)

    assert {f.name for f, _ in files} == {"a.md", "b.txt"}
    assert skipped == []


def test_unsupported_extension_is_collected_not_dropped(tmp_path):
    (tmp_path / "note.md").write_text("conteúdo", encoding="utf-8")
    (tmp_path / "invoice.pdf").write_text("not really a pdf", encoding="utf-8")
    (tmp_path / "contract.docx").write_text("not really a docx", encoding="utf-8")
    skipped: list[tuple[Path, str]] = []

    files = iter_files([str(tmp_path)], skipped_out=skipped)

    assert {f.name for f, _ in files} == {"note.md"}
    skipped_names = {f.name for f, reason in skipped}
    assert skipped_names == {"invoice.pdf", "contract.docx"}
    assert all(reason == "unsupported_extension" for _, reason in skipped)


def test_single_file_path_also_reports_when_skipped(tmp_path):
    pdf = tmp_path / "solo.pdf"
    pdf.write_text("x", encoding="utf-8")
    skipped: list[tuple[Path, str]] = []

    files = iter_files([str(pdf)], skipped_out=skipped)

    assert files == []
    assert skipped == [(pdf, "unsupported_extension")]


def test_skipped_out_is_optional_and_backward_compatible(tmp_path):
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "b.pdf").write_text("x", encoding="utf-8")
    # No skipped_out passed: must not raise, and behaves exactly as before.
    files = iter_files([str(tmp_path)])
    assert {f.name for f, _ in files} == {"a.md"}
