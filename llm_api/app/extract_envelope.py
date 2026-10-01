"""Shared HTTP error envelope for /nfExtract and /boletoExtract.

Bike Anjo / zap clients read `error.message` first, then fall back to `errors[0]`.
Keep both keys on status=error responses.
"""
from __future__ import annotations


def classify_extract_error_code(message: str) -> str:
    low = (message or "").lower()
    if (
        "timeout" in low
        or "timed out" in low
        or "não respondeu" in low
        or "nao respondeu" in low
    ):
        return "timeout"
    if "llm unavailable" in low or "ollama" in low:
        return "model_error"
    return "invalid_request"


def extract_error_dict(errors: list) -> dict[str, str] | None:
    """Build {code, message} from a non-empty errors list, or None."""
    if not errors:
        return None
    msg = errors[0] if isinstance(errors[0], str) else str(errors[0])
    return {"code": classify_extract_error_code(msg), "message": msg}
