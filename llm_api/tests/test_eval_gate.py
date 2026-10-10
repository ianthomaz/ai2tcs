"""scripts/eval_gate.py: the comparison that decides whether a change may go live."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import eval_gate  # noqa: E402


def _snap(rag: dict[str, bool], ops: list[tuple[str, str, bool, bool]] = ()):
    return eval_gate.snapshot(
        [{"question": q, "pass": p} for q, p in rag.items()],
        [{"port": port, "id": cid, "pass": p, "hard": h} for port, cid, p, h in ops],
    )


def test_same_results_pass_the_gate():
    base = _snap({"q1": True, "q2": False})
    problems, _ = eval_gate.compare(base, _snap({"q1": True, "q2": False}))
    assert problems == []


def test_a_case_that_passed_and_now_fails_is_a_regression():
    problems, _ = eval_gate.compare(_snap({"q1": True, "q2": True}), _snap({"q1": True, "q2": False}))
    assert any("passava e agora falha: rag:q2" in p for p in problems)


def test_hard_case_failing_fails_even_without_baseline():
    current = _snap({}, [("feedbackTriage", "t01", False, True)])
    problems, notes = eval_gate.compare(None, current)
    assert problems == ["caso obrigatório falhou: feedbackTriage:t01"]
    assert any("--save-baseline" in n for n in notes)


def test_improvements_and_new_cases_only_inform():
    base = _snap({"q1": False})
    problems, notes = eval_gate.compare(base, _snap({"q1": True, "q9": False}))
    assert problems == []
    assert "melhorou: rag:q1" in notes and any("caso novo: rag:q9" in n for n in notes)


def test_rate_drop_beyond_tolerance_fails():
    base = _snap({"a": True, "b": True, "c": True, "d": True})
    now = _snap({"a": True, "b": True, "c": True, "d": True, "e": False, "f": False})
    problems, _ = eval_gate.compare(base, now, tolerance=0.1)
    assert any("taxa caiu" in p for p in problems)
    problems, _ = eval_gate.compare(base, now, tolerance=0.5)
    assert problems == []
