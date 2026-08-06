"""Zap shadow-to-eval-set JSONL shape is accepted by import_eval_set."""
import json
from pathlib import Path

from scripts.import_eval_set import load_rows, normalize_row, unknown_fields


def test_zap_style_jsonl_normalizes(tmp_path: Path):
    line = {
        "project_id": "bikeanjoall_2026",
        "question": "tem EBA em Natal?",
        "forbidden_keywords": ["telemóvel", "De nada"],
        "max_chars": 280,
        "system_prompt": "Canal WhatsApp Bike Anjo",
        # Zap may attach extras; importer drops them with a warning.
        "shadow_job_id": "abc-123",
        "rated_at": "2026-08-06T12:00:00Z",
    }
    p = tmp_path / "export.jsonl"
    p.write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = load_rows(p)
    assert len(rows) == 1
    row, problems = normalize_row(rows[0], index=0)
    assert problems == []
    assert row is not None
    assert row["project_id"] == "bikeanjoall_2026"
    assert row["question"] == "tem EBA em Natal?"
    assert row["forbidden_keywords"] == ["telemóvel", "De nada"]
    assert row["max_chars"] == 280
    assert row["system_prompt"] == "Canal WhatsApp Bike Anjo"
    assert "shadow_job_id" in unknown_fields(rows[0])
