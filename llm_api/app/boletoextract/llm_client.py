"""Ollama helper for boleto extraction enrichment."""
from __future__ import annotations

import asyncio
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


async def enrich_boleto_with_local_llm(
    *,
    ollama_host: str,
    model: str,
    base_data: dict[str, Any],
    extracted_text: str,
    timeout_s: float = 120.0,
    max_retries: int = 2,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    prompt = (
        "You are a Brazilian bank slip (boleto) extraction assistant.\n"
        "Return ONLY valid JSON with the exact same keys as input.\n"
        "Use JSON null when unknown.\n"
        "beneficiary_document = CNPJ/CPF of who receives payment (cedente/beneficiário).\n"
        "payer_document = CNPJ/CPF of who pays (sacado/pagador).\n"
        "Never swap beneficiary and payer.\n"
        "digitable_line = digits only (47 or 48). barcode = 44 digits.\n"
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
        "options": {"temperature": 0.1, "num_predict": 900},
        "stream": False,
    }
    url = f"{ollama_host.rstrip('/')}/api/chat"
    timeout_cfg = httpx.Timeout(connect=20.0, read=timeout_s, write=20.0, pool=20.0)
    last_error: str | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                content = r.json().get("message", {}).get("content", "")
                parsed = _extract_json(content)
                if parsed:
                    return parsed, warnings
                warnings.append("LLM returned no JSON; using heuristic extraction only.")
                return {}, warnings
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (attempt + 1))
    warnings.append(f"LLM enrichment failed: {last_error or 'unknown error'}")
    return {}, warnings
