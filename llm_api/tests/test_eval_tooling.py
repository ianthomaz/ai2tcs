"""Tests for the eval tooling: dataset intake and run comparison.

These scripts are what makes "before vs after" arguable, so their pure parts are
tested. Nothing here touches the request path or needs a running service.
"""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


import_eval_set = _load("import_eval_set")
eval_rag = _load("eval_rag")


# --- intake ---------------------------------------------------------------


def test_normalize_row_keeps_only_scored_fields():
    row, problems = import_eval_set.normalize_row(
        {
            "project_id": " p1 ",
            "question": " Como faço?  ",
            "expected_keywords": ["a", " b ", ""],
            "max_chars": 300,
            "rating": "great",
            "answer_id": "xyz",
        },
        index=1,
    )
    assert problems == []
    assert row["project_id"] == "p1"
    assert row["question"] == "Como faço?"
    assert row["expected_keywords"] == ["a", "b"]
    assert row["max_chars"] == 300
    # Fields eval_rag does not score never enter the dataset.
    assert "rating" not in row and "answer_id" not in row


@pytest.mark.parametrize(
    "raw,expected_problem",
    [
        ({"question": "q"}, "project_id"),
        ({"project_id": "p", "question": "   "}, "question"),
        ({"project_id": "p", "question": "q", "max_chars": 0}, "max_chars"),
        ({"project_id": "p", "question": "q", "max_chars": True}, "max_chars"),
        ({"project_id": "p", "question": "q", "expected_keywords": "nope"}, "expected_keywords"),
        ({"project_id": "p", "question": "q", "model": ""}, "model"),
    ],
)
def test_normalize_row_rejects_bad_input(raw, expected_problem):
    row, problems = import_eval_set.normalize_row(raw, index=7)
    assert row is None
    assert any(expected_problem in p for p in problems)
    assert all(p.startswith("row 7:") for p in problems)


def test_merge_is_idempotent_and_preserves_curation():
    existing = [{"project_id": "p1", "question": "O que é?", "expected_keywords": ["curado"]}]
    incoming = [
        {"project_id": "p1", "question": "  o QUE é?  ", "expected_keywords": []},  # same key
        {"project_id": "p1", "question": "Outra coisa"},
        {"project_id": "p2", "question": "O que é?"},  # same text, other project
    ]
    merged, added, skipped = import_eval_set.merge_rows(existing, incoming)
    assert (added, skipped) == (2, 1)
    # Human curation already in the dataset is never overwritten by an import.
    assert merged[0]["expected_keywords"] == ["curado"]

    again, added_again, skipped_again = import_eval_set.merge_rows(merged, incoming)
    assert (added_again, skipped_again) == (0, 3)
    assert len(again) == len(merged)


def test_load_rows_accepts_both_json_and_jsonl(tmp_path):
    array = tmp_path / "a.json"
    array.write_text('[{"project_id": "p", "question": "q"}]', encoding="utf-8")
    lines = tmp_path / "b.jsonl"
    lines.write_text('{"project_id": "p", "question": "q"}\n\n{"project_id":"p","question":"r"}\n', encoding="utf-8")
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")

    assert len(import_eval_set.load_rows(array)) == 1
    assert len(import_eval_set.load_rows(lines)) == 2  # blank line ignored
    assert import_eval_set.load_rows(empty) == []


def test_load_rows_reports_the_bad_line(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"project_id":"p","question":"q"}\nNOT JSON\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        import_eval_set.load_rows(bad)


def test_dataset_on_disk_matches_the_intake_contract():
    """The committed dataset must stay loadable by the importer and the runner."""
    dataset = Path(__file__).resolve().parent / "eval" / "eval_questions.json"
    rows = json.loads(dataset.read_text(encoding="utf-8"))
    for i, raw in enumerate(rows, start=1):
        row, problems = import_eval_set.normalize_row(raw, index=i)
        assert problems == [], problems
        assert row is not None


# --- run comparison -------------------------------------------------------


def test_percentile_uses_nearest_rank():
    assert eval_rag.percentile([], 95) == 0.0
    assert eval_rag.percentile([5.0], 95) == 5.0
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert eval_rag.percentile(values, 50) == 5.0
    assert eval_rag.percentile(values, 95) == 10.0
    # p95 must never fall below p50, whatever the sample size.
    for n in range(1, 12):
        sample = [float(i) for i in range(n)]
        assert eval_rag.percentile(sample, 95) >= eval_rag.percentile(sample, 50)


def test_summarize_counts_and_latency():
    rows = [
        {"pass": True, "latency_s": 2.0},
        {"pass": False, "latency_s": 10.0},
        {"pass": True, "latency_s": 4.0},
    ]
    s = eval_rag.summarize(rows)
    assert (s["total"], s["passed"], s["failed"]) == (3, 2, 1)
    assert s["pass_rate"] == pytest.approx(0.6667, abs=1e-4)
    assert s["latency_max"] == 10.0


def test_config_diff_surfaces_the_flag_that_moved():
    before = {"policies": {"rag_rerank_enabled": False, "max_chunks_to_retrieve": 5}}
    after = {"policies": {"rag_rerank_enabled": True, "max_chunks_to_retrieve": 5}}
    assert eval_rag.config_diff(before, after) == [("policies.rag_rerank_enabled", False, True)]
    assert eval_rag.config_diff(before, before) == []
    # A project with no config at all still compares cleanly.
    assert eval_rag.config_diff(None, None) == []
    assert eval_rag.config_diff(None, {"a": 1}) == [("a", None, 1)]


def test_compare_reports_verdict_flips(capsys):
    def result(pass_first: bool, rerank: bool, p95: float) -> dict:
        return {
            "run": {"timestamp": "2026-08-05T10:00:00+00:00", "dataset": "tests/eval/eval_questions.json"},
            "projects": {"p1": {"policies": {"rag_rerank_enabled": rerank}}},
            "summary": {"total": 1, "passed": int(pass_first), "failed": int(not pass_first),
                        "pass_rate": float(pass_first), "latency_p50": 5.0, "latency_p95": p95, "latency_max": p95},
            "rows": [{"project_id": "p1", "question": "q", "pass": pass_first, "note": "ok", "latency_s": 5.0}],
        }

    eval_rag.print_comparison(result(False, False, 20.0), result(True, True, 24.0))
    out = capsys.readouterr().out
    assert "FAIL→PASS" in out
    assert "policies.rag_rerank_enabled" in out
    # Rendered as JSON, matching how the value looks in config_json.
    assert "false → true" in out


def test_compare_is_quiet_when_nothing_moved(capsys):
    run = {
        "run": {"timestamp": "t", "dataset": "d"},
        "projects": {"p1": {"policies": {"rag_rerank_enabled": True}}},
        "summary": {"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0,
                    "latency_p50": 5.0, "latency_p95": 5.0, "latency_max": 5.0},
        "rows": [{"project_id": "p1", "question": "q", "pass": True, "note": "ok", "latency_s": 5.0}],
    }
    eval_rag.print_comparison(run, run)
    out = capsys.readouterr().out
    assert "nenhuma pergunta mudou de veredicto" in out
    assert "configuração idêntica" in out


def test_load_result_rejects_a_file_that_is_not_a_run(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"rows": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'run'"):
        eval_rag.load_result(p)
