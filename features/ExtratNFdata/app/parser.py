"""Document parsing and extraction pipeline (Python first, LLM second)."""
from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from app.llm_client import enrich_with_local_llm

_NF_PLACEHOLDER_STRINGS = frozenset(
    {
        "não informado",
        "nao informado",
        "não disponível",
        "nao disponivel",
        "n/d",
        "n.d.",
        "nd",
        "n/a",
        "na",
        "desconhecido",
        "unknown",
        "não se aplica",
        "nao se aplica",
        "sem informação",
        "sem informacao",
        "indisponível",
        "indisponivel",
        "-",
        "---",
    }
)


def _normalize_nf_llm_value(value: Any) -> Any:
    """Coerce LLM placeholder strings to None so JSON/orchestrators get null, not prose."""
    if value is None:
        return None
    if isinstance(value, str):
        t = value.strip()
        if not t:
            return None
        tl = t.lower()
        if tl in ("null", "none", "nil"):
            return None
        if tl in _NF_PLACEHOLDER_STRINGS:
            return None
        if tl.rstrip(".") in _NF_PLACEHOLDER_STRINGS:
            return None
    return value


def _digits(value: str | None) -> str | None:
    if not value:
        return None
    d = re.sub(r"\D", "", value)
    return d or None


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    normalized = value.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _find_text_by_localname(root: ET.Element, names: list[str]) -> str | None:
    names_set = set(names)
    for elem in root.iter():
        tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag_name in names_set and elem.text and elem.text.strip():
            return elem.text.strip()
    return None


def detect_document_type(file_name: str | None, raw_bytes: bytes) -> str:
    if raw_bytes[:5] == b"%PDF-":
        return "pdf"
    if raw_bytes.lstrip().startswith(b"<"):
        return "xml"
    suffix = Path(file_name or "").suffix.lower()
    if suffix in {".xml"}:
        return "xml"
    if suffix in {".pdf"}:
        return "pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}:
        return "img"
    return "unknown"


def extract_from_xml(raw_bytes: bytes) -> tuple[dict[str, Any], str]:
    root = ET.fromstring(raw_bytes)
    supplier_name = _find_text_by_localname(root, ["xNome", "PrestadorServico", "RazaoSocial"])
    supplier_cnpj = _find_text_by_localname(root, ["CNPJ", "CpfCnpj"])
    nf_number = _find_text_by_localname(root, ["nNF", "Numero", "InfNfseNumero"])
    issue_date = _find_text_by_localname(root, ["dhEmi", "dEmi", "DataEmissao"])
    total = _find_text_by_localname(root, ["vNF", "ValorServicos", "ValorLiquidoNfse"])
    amount_tax = _find_text_by_localname(root, ["vISS", "ValorIss", "ValorIssRetido"])
    raw_text = ET.tostring(root, encoding="unicode")[:6000]

    data: dict[str, Any] = {
        "supplier_name": supplier_name,
        "supplier_code": _digits(supplier_cnpj),
        "nf_number": nf_number,
        "issue_date": issue_date[:10] if issue_date else None,
        "amount": _to_float(total),
        "amount_tax": _to_float(amount_tax),
        "amount_type": "total",
    }
    if data.get("amount_tax"):
        data["amount_type"] = "imposto_retido"
    return data, raw_text


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("pypdf is required for PDF extraction.") from exc

    reader = PdfReader(io.BytesIO(raw_bytes))
    chunks: list[str] = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _extract_img_text(raw_bytes: bytes) -> str:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("pytesseract + pillow are required for image OCR.") from exc

    image = Image.open(io.BytesIO(raw_bytes))
    return pytesseract.image_to_string(image, lang="por+eng")


def extract_from_text_heuristics(text: str) -> dict[str, Any]:
    compact = " ".join(text.split())
    cnpjs = re.findall(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", compact)
    supplier_code = _digits(cnpjs[0]) if cnpjs else None
    nf_number_match = re.search(r"(?:nfs-e|nfse|nota fiscal)\D{0,30}(\d{1,8})", compact, re.IGNORECASE)
    if not nf_number_match:
        nf_number_match = re.search(r"(?:n[úu]mero)\D{0,8}(\d{1,8})", compact, re.IGNORECASE)
    amount = _extract_total_amount(compact)

    data: dict[str, Any] = {
        "supplier_code": supplier_code,
        "nf_number": nf_number_match.group(1) if nf_number_match else None,
        "amount": amount,
    }
    if data.get("amount") is not None:
        data["amount_type"] = "total"
    description = _extract_description_section(text)
    if description:
        data["description"] = description
    payment_data = _extract_payment_from_text(text)
    data.update({k: v for k, v in payment_data.items() if v not in (None, "", "unknown")})
    return data


def _extract_total_amount(compact_text: str) -> float | None:
    priority_patterns = [
        r"valor\s+total\s+da\s+nota\D{0,20}(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"valor\s+liquido\D{0,20}(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"\btotal\D{0,20}(\d{1,3}(?:\.\d{3})*,\d{2})",
    ]
    for pattern in priority_patterns:
        match = re.search(pattern, compact_text, re.IGNORECASE)
        if match:
            return _to_float(match.group(1))

    all_values = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})", compact_text)
    parsed = [_to_float(v) for v in all_values]
    parsed = [v for v in parsed if v is not None]
    if not parsed:
        return None

    # Skip very small values that are often taxes/fees and keep the largest monetary value.
    return max(parsed)


def _extract_description_section(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    markers = [
        "dados adicionais",
        "informações complementares",
        "informacoes complementares",
        "discriminação dos serviços",
        "discriminacao dos servicos",
        "descrição",
        "descricao",
        "observações",
        "observacoes",
    ]
    lowered = cleaned.lower()
    start = -1
    for marker in markers:
        idx = lowered.find(marker)
        if idx >= 0 and (start == -1 or idx < start):
            start = idx
    if start >= 0:
        return cleaned[start : start + 1800].strip()
    # Fallback: keep tail because many invoices place details at the end.
    tail = cleaned[-1800:].strip()
    return tail if tail else None


def _extract_payment_from_text(text: str) -> dict[str, Any]:
    compact = " ".join(text.split())
    lowered = compact.lower()

    pix_key = None
    pix_match = re.search(
        r"(?:pix[:\s-]*)([0-9A-Za-z@._+\-/]{8,}|"
        r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|"
        r"\d{3}\.?\d{3}\.?\d{3}-?\d{2})",
        compact,
        re.IGNORECASE,
    )
    if pix_match:
        pix_key = pix_match.group(1).strip()

    bank_match = re.search(
        r"\b(banco\s+[a-zA-Z]+|santander|itau|itaú|bradesco|caixa|nubank|inter|sicredi|bb|banco do brasil)\b",
        lowered,
        re.IGNORECASE,
    )
    agency_match = re.search(r"\b(?:ag|ag[êe]ncia)\s*[:\-]?\s*(\d{3,6})\b", compact, re.IGNORECASE)
    account_match = re.search(
        r"\b(?:c\/?c|conta(?:\s*corrente)?)\s*[:\-]?\s*([\d.\-\/xX]{4,20})\b",
        compact,
        re.IGNORECASE,
    )

    return {
        "payment_pixCode": pix_key,
        "payment_bank": bank_match.group(1).upper() if bank_match else None,
        "payment_bank_agency": agency_match.group(1) if agency_match else None,
        "payment_bank_account": account_match.group(1) if account_match else None,
    }


async def fetch_document_from_url(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed.")
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        file_name = Path(parsed.path).name or "remote_document"
        return r.content, file_name


def read_document_from_path(path: str) -> tuple[bytes, str]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    return p.read_bytes(), p.name


async def run_extraction_pipeline(
    *,
    source_type: str,
    file_name: str | None,
    raw_bytes: bytes,
    ollama_host: str,
    ollama_model: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []

    doc_type = detect_document_type(file_name, raw_bytes)
    base: dict[str, Any] = {
        "supplier_name": None,
        "supplier_code": None,
        "nf_number": None,
        "issue_date": None,
        "amount": None,
        "amount_type": "unknown",
        "amount_deposit": None,
        "amount_tax": None,
        "description": None,
        "payment_pixCode": None,
        "payment_bank": None,
        "payment_bank_agency": None,
        "payment_bank_account": None,
        "payment_bank_account_type": "unknown",
        "payment_receiver_name": None,
        "payment_receiver_document": None,
    }
    extracted_text = ""

    try:
        if doc_type == "xml":
            xml_data, extracted_text = extract_from_xml(raw_bytes)
            base.update({k: v for k, v in xml_data.items() if v is not None})
        elif doc_type == "pdf":
            extracted_text = _extract_pdf_text(raw_bytes)
            base.update({k: v for k, v in extract_from_text_heuristics(extracted_text).items() if v is not None})
        elif doc_type == "img":
            extracted_text = _extract_img_text(raw_bytes)
            base.update({k: v for k, v in extract_from_text_heuristics(extracted_text).items() if v is not None})
        else:
            errors.append("Unsupported document type. Send XML, PDF, or image.")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    llm_data, llm_warnings = await enrich_with_local_llm(
        ollama_host=ollama_host,
        model=ollama_model,
        base_data=base,
        extracted_text=extracted_text,
    )
    warnings.extend(llm_warnings)
    for key, value in llm_data.items():
        if key not in base:
            continue
        normalized = _normalize_nf_llm_value(value)
        if normalized not in ("", None):
            base[key] = normalized

    confidence_by_field: dict[str, float] = {}
    populated = 0
    for k, v in base.items():
        score = 0.0 if v in (None, "", "unknown") else 0.85
        confidence_by_field[k] = score
        if score > 0:
            populated += 1
    confidence = round(populated / max(len(base), 1), 4)

    return {
        "status": "error" if errors else "ok",
        "source_type": source_type,
        "document_type": doc_type,
        "file_name": file_name,
        **base,
        "confidence": confidence,
        "confidence_by_field": confidence_by_field,
        "warnings": warnings,
        "errors": errors,
        "raw_text_excerpt": extracted_text[:1200] if extracted_text else None,
    }
