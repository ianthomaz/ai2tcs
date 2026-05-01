"""In-process counters for STT observability (exposed via GET /metrics)."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_stt_completed: int = 0
_stt_failed: int = 0
_stt_seconds_sum: float = 0.0


def record_stt_success(duration_seconds: float) -> None:
    global _stt_completed, _stt_seconds_sum
    with _lock:
        _stt_completed += 1
        _stt_seconds_sum += max(0.0, duration_seconds)


def record_stt_failure() -> None:
    global _stt_failed
    with _lock:
        _stt_failed += 1


def stt_metric_lines() -> list[str]:
    """Prometheus-style lines (no HELP/TYPE for parity with existing /metrics)."""
    with _lock:
        completed = _stt_completed
        failed = _stt_failed
        sec_sum = _stt_seconds_sum
    lines = [
        f"llm_stt_completed_total {completed}",
        f"llm_stt_failed_total {failed}",
        f"llm_stt_transcribe_seconds_sum {sec_sum:.6f}",
    ]
    if completed > 0:
        lines.append(f"llm_stt_transcribe_seconds_avg {sec_sum / completed:.6f}")
    return lines
