"""Boleto parsing: heuristics + optional LLM enrichment."""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.boletoextract.llm_client import enrich_boleto_with_local_llm
from app.nfextract.parser import (
    detect_document_type,
    extract_pdf_text_with_fallbacks,
    read_document_from_path,
)

_DIGIT_LINE_RE = re.compile(r"\d[\d.\s]{40,}\d")
_BARCODE_RE = re.compile(r"\d{44}")

_BENEFICIARY_LABELS = (
    r"benefici[áa]rio",
    r"cedente",
    r"beneficiary",
)
_PAYER_LABELS = (
    r"sacado",
    r"pagador",
    r"payer",
)


def _digits(value: str | None) -> str | None:
    if not value:
        return None
    d = re.sub(r"\D", "", value)
    return d or None


def _cnpj_checksum_valid(d14: str) -> bool:
    if not d14 or len(d14) != 14 or not d14.isdigit():
        return False
    if len(set(d14)) == 1:
        return False
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    digits = [int(x) for x in d14]
    s = sum(digits[i] * w1[i] for i in range(12))
    r = s % 11
    v1 = 0 if r < 2 else 11 - r
    if v1 != digits[12]:
        return False
    s = sum(digits[i] * w2[i] for i in range(13))
    r = s % 11
    v2 = 0 if r < 2 else 11 - r
    return v2 == digits[13]


def _mod10(number: str) -> int:
    total = 0
    weight = 2
    for ch in reversed(number):
        n = int(ch) * weight
        if n > 9:
            n = sum(int(x) for x in str(n))
        total += n
        weight = 1 if weight == 2 else 2
    remainder = total % 10
    return 0 if remainder == 0 else 10 - remainder


def _mod11(number: str, base: int = 9) -> int:
    weights = list(range(base, 1, -1))
    while len(weights) < len(number):
        weights.insert(0, base)
    total = sum(int(number[i]) * weights[i] for i in range(len(number)))
    remainder = total % 11
    if remainder in (0, 1):
        return 0
    if remainder == 10:
        return 1
    return 11 - remainder


def validate_digitable_line(digits: str) -> bool:
    """Validate 47-digit (collection) or 48-digit (compensation) digitable line."""
    if len(digits) not in (47, 48):
        return False
    if len(digits) == 47:
        blocks = [digits[0:9], digits[10:20], digits[21:31], digits[32:47]]
        for block in blocks[:3]:
            body, dv = block[:-1], block[-1]
            if str(_mod10(body)) != dv:
                return False
        general = digits[0:4] + digits[32:47]
        body, dv = general[:-1], general[-1]
        return str(_mod11(body)) == dv
    # 48-digit compensation slip
    blocks = [digits[0:11], digits[12:23], digits[24:35], digits[36:47]]
    for block in blocks[:3]:
        body, dv = block[:-1], block[-1]
        if str(_mod10(body)) != dv:
            return False
    return True


def _extract_digitable_line(text: str) -> str | None:
    for match in _DIGIT_LINE_RE.finditer(text):
        digits = _digits(match.group(0))
        if not digits:
            continue
        if len(digits) in (47, 48) and validate_digitable_line(digits):
            return digits
    return None


def _extract_barcode(text: str) -> str | None:
    for match in _BARCODE_RE.finditer(re.sub(r"\s+", "", text)):
        code = match.group(0)
        if len(code) == 44:
            return code
    return None


def _extract_labeled_document(text: str, label_patterns: tuple[str, ...]) -> str | None:
    for pat in label_patterns:
        block_m = re.search(
            rf"(?is)({pat}\s*[:\-]?[^\n]*(?:\n(?!(?:{'|'.join(_BENEFICIARY_LABELS + _PAYER_LABELS)})\s*[:\-])[^\n]*){{0,4}})",
            text,
        )
        if block_m:
            block = block_m.group(1)
            doc_match = re.search(
                r"(?:CPF/CNPJ\s*[:\-]?\s*)?(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2})",
                block,
            )
            if doc_match:
                d = _digits(doc_match.group(1))
                if d and (len(d) == 11 or (len(d) == 14 and _cnpj_checksum_valid(d))):
                    return d
        m = re.search(
            rf"(?is){pat}\s*[:\-]?\s*(?:CPF/CNPJ\s*[:\-]?\s*)?([^\n]+)",
            text,
        )
        if not m:
            continue
        line = m.group(1)
        doc_match = re.search(r"(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2})", line)
        if doc_match:
            d = _digits(doc_match.group(1))
            if d and (len(d) == 11 or (len(d) == 14 and _cnpj_checksum_valid(d))):
                return d
    return None


def _extract_labeled_name(text: str, label_patterns: tuple[str, ...]) -> str | None:
    for pat in label_patterns:
        m = re.search(rf"(?is){pat}\s*[:\-]?\s*([^\n]+)", text)
        if not m:
            continue
        line = m.group(1).strip()
        line = re.sub(r"\s*CPF/CNPJ.*$", "", line, flags=re.IGNORECASE).strip()
        if line and len(line) > 2:
            return line[:200]
    return None


def _extract_due_date(text: str) -> str | None:
    m = re.search(
        r"(?is)vencimento\s*[:\-]?\s*(\d{2}[/.-]\d{2}[/.-]\d{2,4})",
        text,
    )
    if m:
        return m.group(1).replace(".", "/")
    return None


def _extract_amount(text: str) -> float | None:
    m = re.search(
        r"(?is)(?:valor\s+(?:do\s+)?documento|valor)\s*[:\-]?\s*R?\$?\s*([\d.,]+)",
        text,
    )
    if not m:
        return None
    raw = m.group(1).replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_bank_code(text: str, digitable_line: str | None) -> str | None:
    if digitable_line and len(digitable_line) >= 3:
        return digitable_line[:3]
    m = re.search(r"(?is)banco\s*[:\-]?\s*(\d{3})", text)
    return m.group(1) if m else None


def _extract_img_text(raw_bytes: bytes) -> str:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    img = Image.open(io.BytesIO(raw_bytes))
    return pytesseract.image_to_string(img, lang="por+eng")


def extract_from_text_heuristics(text: str) -> dict[str, Any]:
    digitable = _extract_digitable_line(text)
    barcode = _extract_barcode(text)
    beneficiary_doc = _extract_labeled_document(text, _BENEFICIARY_LABELS)
    payer_doc = _extract_labeled_document(text, _PAYER_LABELS)
    if beneficiary_doc and payer_doc and beneficiary_doc == payer_doc:
        payer_doc = None
    return {
        "beneficiary_name": _extract_labeled_name(text, _BENEFICIARY_LABELS),
        "beneficiary_document": beneficiary_doc,
        "payer_name": _extract_labeled_name(text, _PAYER_LABELS),
        "payer_document": payer_doc,
        "digitable_line": digitable,
        "barcode": barcode,
        "due_date": _extract_due_date(text),
        "amount": _extract_amount(text),
        "bank_code": _extract_bank_code(text, digitable),
        "document_number": None,
    }


async def fetch_document_from_url(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed.")
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        file_name = Path(parsed.path).name or "remote_boleto"
        return r.content, file_name


def _confidence_for_boleto_field(field: str, value: Any, heuristic: dict[str, Any]) -> float:
    if value in (None, "", "unknown"):
        return 0.0
    if field in ("digitable_line", "barcode") and heuristic.get(field) == value:
        return 0.95
    if heuristic.get(field) == value:
        return 0.9
    return 0.6


async def run_boleto_extraction_pipeline(
    *,
    source_type: str,
    file_name: str | None,
    raw_bytes: bytes,
    ollama_host: str,
    ollama_model: str,
    ollama_timeout_s: float = 120.0,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    doc_type = detect_document_type(file_name, raw_bytes)
    base: dict[str, Any] = {
        "beneficiary_name": None,
        "beneficiary_document": None,
        "payer_name": None,
        "payer_document": None,
        "digitable_line": None,
        "barcode": None,
        "due_date": None,
        "amount": None,
        "bank_code": None,
        "document_number": None,
    }
    extracted_text = ""
    try:
        if doc_type == "pdf":
            extracted_text, pdf_warnings = extract_pdf_text_with_fallbacks(raw_bytes)
            warnings.extend(pdf_warnings)
        elif doc_type == "img":
            extracted_text = _extract_img_text(raw_bytes)
        else:
            errors.append("Unsupported document type for boleto. Send PDF or image.")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    if extracted_text:
        heur = extract_from_text_heuristics(extracted_text)
        base.update({k: v for k, v in heur.items() if v is not None})
        if base.get("beneficiary_document") and base.get("payer_document") is None:
            warnings.append("Payer document not found; verify beneficiary vs payer manually.")
        if base.get("digitable_line") is None and base.get("barcode") is None:
            warnings.append("No valid digitable line or barcode detected.")

    pre_llm = dict(base)
    llm_data, llm_warnings = await enrich_boleto_with_local_llm(
        ollama_host=ollama_host,
        model=ollama_model,
        base_data=base,
        extracted_text=extracted_text,
        timeout_s=ollama_timeout_s,
    )
    warnings.extend(llm_warnings)
    for key, value in llm_data.items():
        if key not in base or value in (None, "", "unknown"):
            continue
        if key in ("beneficiary_document", "payer_document"):
            d = _digits(str(value))
            if d and (len(d) == 11 or (len(d) == 14 and _cnpj_checksum_valid(d))):
                base[key] = d
            continue
        if key == "digitable_line":
            d = _digits(str(value))
            if d and validate_digitable_line(d):
                base[key] = d
            continue
        base[key] = value

    if (
        base.get("beneficiary_document")
        and base.get("payer_document")
        and base["beneficiary_document"] == base["payer_document"]
    ):
        warnings.append("Beneficiary and payer documents are identical; payer cleared.")
        base["payer_document"] = None

    if pre_llm.get("beneficiary_document") and base.get("beneficiary_document") != pre_llm["beneficiary_document"]:
        warnings.append("LLM changed beneficiary document; kept heuristic value.")
        base["beneficiary_document"] = pre_llm["beneficiary_document"]
    if pre_llm.get("payer_document") and base.get("payer_document") != pre_llm.get("payer_document"):
        if pre_llm["payer_document"]:
            base["payer_document"] = pre_llm["payer_document"]

    confidence_by_field = {
        k: _confidence_for_boleto_field(k, v, pre_llm) for k, v in base.items()
    }
    populated = sum(1 for s in confidence_by_field.values() if s > 0)
    return {
        "status": "error" if errors else "ok",
        "source_type": source_type,
        "document_type": doc_type,
        "file_name": file_name,
        **base,
        "confidence": round(populated / max(len(base), 1), 4),
        "confidence_by_field": confidence_by_field,
        "warnings": warnings,
        "errors": errors,
        "raw_text_excerpt": extracted_text[:1200] if extracted_text else None,
    }
