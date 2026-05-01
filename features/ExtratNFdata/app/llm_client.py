"""Ollama helper for JSON normalization and enrichment."""
from __future__ import annotations

import json
import re
from typing import Any

import httpx


def _extract_json(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


async def enrich_with_local_llm(
    *,
    ollama_host: str,
    model: str,
    base_data: dict[str, Any],
    extracted_text: str,
    timeout_s: float = 45.0,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    prompt = (
        "You are a Brazilian invoice extraction assistant.\n"
        "Return ONLY valid JSON with the exact same keys as input.\n"
        "Use JSON null when a value is unknown or not found in the document.\n"
        "Do not invent values.\n"
        "Critical for downstream parsers: never use human-readable placeholders for missing "
        "data. For payment fields (payment_pixCode, payment_bank, payment_bank_agency, "
        "payment_bank_account, payment_bank_account_type, payment_receiver_name, "
        "payment_receiver_document) and any optional field, use JSON null only — not "
        "Portuguese or English phrases like \"não informado\", \"não disponível\", "
        "\"desconhecido\", \"N/A\", or \"sem informação\".\n"
        "Input data and OCR text may be noisy. Prioritize reliable values.\n"
        "Important: payment details can appear in free-text sections like "
        "'descricao', 'discriminacao', 'dados adicionais', or similar names.\n"
        "If PIX and bank transfer details both appear, fill both PIX and bank fields.\n"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"BASE_JSON:\n{json.dumps(base_data, ensure_ascii=False)}\n\n"
                    f"DOCUMENT_TEXT:\n{extracted_text[:12000]}"
                ),
            },
        ],
        "options": {"temperature": 0.1, "num_predict": 1200},
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(f"{ollama_host.rstrip('/')}/api/chat", json=payload)
            r.raise_for_status()
            content = ((r.json().get("message") or {}).get("content") or "").strip()
            parsed = _extract_json(content)
            if not parsed:
                warnings.append("LLM returned non-JSON content; kept Python extraction.")
            return parsed, warnings
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip() or exc.__class__.__name__
        warnings.append(f"LLM unavailable: {msg}")
        return {}, warnings
