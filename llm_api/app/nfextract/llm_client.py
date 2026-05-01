"""Ollama helper for NF extraction enrichment."""
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


async def enrich_with_local_llm(
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
        "Never use 0 for unknown monetary amounts; use JSON null.\n"
        "Input data and OCR text may be noisy. Prioritize reliable values.\n"
        "For supplier_code: only the 14-digit CNPJ of the service provider (prestador/emitente), "
        "or 11-digit CPF when the issuer is an individual. "
        "Never use the NFS-e access key (44 digits) or any substring of it.\n"
        "For service_recipient_code: CNPJ or CPF of the tomador (service recipient / customer) "
        "who received the service — digits only in the JSON string when confident, else null.\n"
        "For payment_type, use one of: \"pix\", \"boleto\", \"transferencia\", \"cartao_credito\", "
        "\"dinheiro\", or null if unclear. Prefer \"pix\" when a Pix key is present; "
        "\"transferencia\" when bank+agency+account without Pix; \"boleto\" when the document "
        "mentions boleto, linha digitável, or barcode; \"cartao_credito\" for credit card; "
        "\"dinheiro\" for cash/espécie.\n"
        "For description: when you output a description and the emission date is known, "
        "the first line MUST be exactly: NF emitida DD/mmm/YYYY where DD is two digits, "
        "mmm is one of jan fev mar abr mai jun jul ago set out nov dez (lowercase Portuguese "
        "month abbreviations), YYYY is four digits. After a newline, add a short human summary "
        "of the service or product — not long OCR dumps, not tax/tributação boilerplate blocks.\n"
        "If the emission date is unknown, set description to null (do not invent a date line).\n"
        "Payment details can appear in free-text sections like descricao, "
        "discriminacao, dados adicionais, or similar names.\n"
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
    timeout_cfg = httpx.Timeout(
        connect=min(20.0, max(5.0, timeout_s * 0.1)),
        read=timeout_s,
        write=min(120.0, timeout_s),
        pool=10.0,
    )
    backoff = 0.5
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                r = await client.post(f"{ollama_host.rstrip('/')}/api/chat", json=payload)
                r.raise_for_status()
                content = ((r.json().get("message") or {}).get("content") or "").strip()
                parsed = _extract_json(content)
                if not parsed:
                    warnings.append("LLM returned non-JSON content; kept Python extraction.")
                if attempt > 0:
                    warnings.append(f"LLM succeeded after {attempt} retry(ies).")
                return parsed, warnings
        except httpx.HTTPStatusError as exc:
            last_error = str(exc).strip() or exc.__class__.__name__
            code = exc.response.status_code if exc.response is not None else 0
            if code in (502, 503, 504) and attempt < max_retries:
                warnings.append(f"LLM HTTP {code}; retrying in {backoff}s ({attempt + 1}/{max_retries}).")
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            warnings.append(f"LLM unavailable: {last_error}")
            return {}, warnings
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, httpx.WriteError) as exc:
            last_error = str(exc).strip() or exc.__class__.__name__
            if attempt < max_retries:
                warnings.append(f"LLM transport error; retrying in {backoff}s ({attempt + 1}/{max_retries}): {last_error}")
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            warnings.append(f"LLM unavailable: {last_error}")
            return {}, warnings
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).strip() or exc.__class__.__name__
            warnings.append(f"LLM unavailable: {msg}")
            return {}, warnings
