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
    _to_float,
    detect_document_type,
    extract_pdf_text_with_fallbacks,
    read_document_from_path,
)

_DIGIT_LINE_RE = re.compile(r"\d[\d.\s]{40,}\d")
_BARCODE_RE = re.compile(r"\d{44}")

# Associação Bike Anjo — taxpayer/payer on guias, never the beneficiary.
BIKE_ANJO_CNPJ = "19515100000189"

_BENEFICIARY_LABELS = (
    r"benefici[áa]rio",
    r"cedente",
    r"beneficiary",
)
_PAYER_LABELS = (
    r"sacado",
    r"pagador",
    r"payer",
    r"contribuinte",
    r"raz[ãa]o\s+social",
)

_GUIA_HINTS = re.compile(
    r"(?is)documento\s+de\s+arrecada|"
    r"\bDARF\b|"
    r"\bDAS\b|"
    r"\bGPS\b|"
    r"\bCOFINS\b|"
    r"\bPIS\b|"
    r"\bCSLL\b|"
    r"\bIRPJ\b|"
    r"(?:^|\s)ISS(?:\s|/|-)|"
    r"receita\s+federal|"
    r"senha\s*\(|"
    r"n[ºo°]?\s*recibo\s+declara"
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
    """Validate 47-digit (bank) or 48-digit (arrecadação/compensation) digitable line."""
    if len(digits) not in (47, 48):
        return False
    # Federal/municipal collection slips (start with 8): accept length; DV schemes vary.
    if len(digits) == 48 and digits.startswith("8"):
        return True
    if len(digits) == 47:
        blocks = [digits[0:9], digits[10:20], digits[21:31], digits[32:47]]
        for block in blocks[:3]:
            body, dv = block[:-1], block[-1]
            if str(_mod10(body)) != dv:
                return False
        general = digits[0:4] + digits[32:47]
        body, dv = general[:-1], general[-1]
        return str(_mod11(body)) == dv
    # 48-digit non-arrecadação (compensation)
    blocks = [digits[0:11], digits[12:23], digits[24:35], digits[36:47]]
    for block in blocks[:3]:
        body, dv = block[:-1], block[-1]
        if str(_mod10(body)) != dv:
            return False
    return True


def is_guia_arrecadacao(text: str, file_name: str | None = None) -> bool:
    blob = f"{file_name or ''}\n{text or ''}"
    if _GUIA_HINTS.search(blob):
        return True
    d = _extract_digitable_line(text or "")
    return bool(d and d.startswith("8") and len(d) == 48)


def _extract_digitable_line(text: str) -> str | None:
    # Spaced arrecadação blocks (11+1)×4 — common on DARF / collection slips.
    spaced = re.search(
        r"(?<!\d)(8\d{10})\s*(\d)\s*(\d{11})\s*(\d)\s*(\d{11})\s*(\d)\s*(\d{11})\s*(\d)(?!\d)",
        text,
    )
    if spaced:
        digits = "".join(spaced.groups())
        if validate_digitable_line(digits):
            return digits

    # Digit-only stream: require arrecadação prefix 8… so we do not glue onto a prior digit
    # (e.g. document number "…2-3" + "8588…" → "38588…").
    only = re.sub(r"\D", "", text)
    for m in re.finditer(r"8\d{47}", only):
        digits = m.group(0)
        if validate_digitable_line(digits):
            return digits

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
        r"(?is)(?:pagar\s+(?:este\s+documento\s+)?at[ée]|vencimento|pagar\s+at[ée])\s*[:\-]?\s*(\d{2}[/.-]\d{2}[/.-]\d{2,4})",
        text,
    )
    if m:
        return m.group(1).replace(".", "/")
    return None


def _parse_brl_amount(raw: str) -> float | None:
    s = raw.strip()
    if not s:
        return None
    # Brazilian: 3.062,04 or 3062,04 — never strip comma as thousands.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # Only dots: if last group has 2 digits treat as decimal (3062.04); else thousands.
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) == 2:
            pass
        else:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _extract_amount(text: str) -> float | None:
    patterns = (
        r"(?is)valor\s+total\s+do\s+documento\s*[:\-]?\s*R?\$?\s*([\d.,]+)",
        r"(?is)valor\s+do\s+documento\s*[:\-]?\s*R?\$?\s*([\d.,]+)",
        r"(?is)valor\s*[:\-]?\s*R?\$?\s*([\d.,]+)",
    )
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        val = _parse_brl_amount(m.group(1))
        if val is not None and val > 0:
            return val
    return None


def _extract_document_number(text: str) -> str | None:
    patterns = (
        r"(?is)n[úu]mero\s+do\s+documento\s*[:\-]?\s*([0-9.\-/]+)",
        r"(?is)n[úu]mero\s*[:\-]?\s*([0-9]{2}\.[0-9.]+-[0-9])",
        r"(?is)n[ºo°]?\s*recibo\s+declara[cç][aã]o\s*[:\-]?\s*(\d+)",
    )
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:80]
    return None


def _extract_bank_code(text: str, digitable_line: str | None) -> str | None:
    if digitable_line and len(digitable_line) >= 3 and not digitable_line.startswith("8"):
        return digitable_line[:3]
    m = re.search(r"(?is)banco\s*[:\-]?\s*(\d{3})", text)
    return m.group(1) if m else None


def _guess_tax_authority(text: str) -> tuple[str | None, str | None]:
    """Return (beneficiary_name, kind_label) for guias when no cedente is printed."""
    t = text or ""
    if re.search(r"(?is)\bCOFINS\b|\bDARF\b|receita\s+federal|arrecada[cç][aã]o\s+de\s+receitas\s+federais", t):
        kind = "COFINS" if re.search(r"(?is)\bCOFINS\b", t) else "tributo federal"
        return f"Receita Federal – {kind}", "federal"
    if re.search(r"(?is)\bISS\b|prefeitura|s[aã]o\s*paulo\s+iss", t):
        return "Prefeitura de São Paulo – ISS", "iss"
    if re.search(r"(?is)\bDAS\b|\bGPS\b", t):
        return "Receita Federal – guia", "federal"
    return "Ente arrecadador", "guia"


def _name_looks_bike_anjo(name: str | None) -> bool:
    if not name:
        return False
    n = name.lower().replace(" ", "")
    return "bikeanjo" in n or "associa" in name.lower() and "bike" in name.lower()


def apply_guia_roles(base: dict[str, Any], text: str) -> dict[str, Any]:
    """On guias, Bike Anjo CNPJ is the payer; tax authority is the beneficiary."""
    out = dict(base)
    ba_as_beneficiary = out.get("beneficiary_document") == BIKE_ANJO_CNPJ or _name_looks_bike_anjo(
        out.get("beneficiary_name")
    )
    if ba_as_beneficiary:
        if not out.get("payer_document"):
            out["payer_document"] = BIKE_ANJO_CNPJ
        if not out.get("payer_name"):
            out["payer_name"] = out.get("beneficiary_name") or "ASSOCIACAO BIKE ANJO"
        auth_name, _ = _guess_tax_authority(text)
        out["beneficiary_name"] = auth_name
        out["beneficiary_document"] = None
    elif not out.get("beneficiary_name") and not out.get("beneficiary_document"):
        auth_name, _ = _guess_tax_authority(text)
        out["beneficiary_name"] = auth_name
        if not out.get("payer_document") and BIKE_ANJO_CNPJ in re.sub(r"\D", "", text):
            out["payer_document"] = BIKE_ANJO_CNPJ
            out["payer_name"] = out.get("payer_name") or "ASSOCIACAO BIKE ANJO"
    # Never leave BA as beneficiary after guia correction.
    if out.get("beneficiary_document") == BIKE_ANJO_CNPJ:
        out["beneficiary_document"] = None
        if _name_looks_bike_anjo(out.get("beneficiary_name")):
            auth_name, _ = _guess_tax_authority(text)
            out["beneficiary_name"] = auth_name
    return out


def _extract_img_text(raw_bytes: bytes) -> str:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    img = Image.open(io.BytesIO(raw_bytes))
    return pytesseract.image_to_string(img, lang="por+eng")


def extract_from_text_heuristics(text: str, file_name: str | None = None) -> dict[str, Any]:
    digitable = _extract_digitable_line(text)
    barcode = _extract_barcode(text)
    beneficiary_doc = _extract_labeled_document(text, _BENEFICIARY_LABELS)
    payer_doc = _extract_labeled_document(text, _PAYER_LABELS)
    if beneficiary_doc and payer_doc and beneficiary_doc == payer_doc:
        payer_doc = None
    data: dict[str, Any] = {
        "beneficiary_name": _extract_labeled_name(text, _BENEFICIARY_LABELS),
        "beneficiary_document": beneficiary_doc,
        "payer_name": _extract_labeled_name(text, _PAYER_LABELS),
        "payer_document": payer_doc,
        "digitable_line": digitable,
        "barcode": barcode,
        "due_date": _extract_due_date(text),
        "amount": _extract_amount(text),
        "bank_code": _extract_bank_code(text, digitable),
        "document_number": _extract_document_number(text),
    }
    if is_guia_arrecadacao(text, file_name):
        # Prominent CNPJ on guias is usually the taxpayer (payer).
        all_cnpjs = re.findall(
            r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}",
            text,
        )
        digs = [_digits(c) for c in all_cnpjs]
        digs = [d for d in digs if d and len(d) == 14 and _cnpj_checksum_valid(d)]
        if BIKE_ANJO_CNPJ in digs and not data.get("payer_document"):
            data["payer_document"] = BIKE_ANJO_CNPJ
        if data.get("beneficiary_document") == BIKE_ANJO_CNPJ or (
            not data.get("beneficiary_document") and BIKE_ANJO_CNPJ in digs
        ):
            data = apply_guia_roles(data, text)
        else:
            data = apply_guia_roles(data, text)
    return data


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


def _sanitize_amount_after_llm(value: Any, heuristic_amount: float | None) -> float | None:
    coerced = _to_float(str(value)) if isinstance(value, str) else value
    if not isinstance(coerced, (int, float)):
        return heuristic_amount
    amount = float(coerced)
    # Guard against collapsed decimals (2014.50 → 201450).
    if heuristic_amount is not None and heuristic_amount > 0:
        if amount >= heuristic_amount * 50 and abs(amount / 100 - heuristic_amount) < 0.02:
            return heuristic_amount
        if amount > heuristic_amount * 10:
            return heuristic_amount
    return amount


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

    guia = False
    if extracted_text:
        heur = extract_from_text_heuristics(extracted_text, file_name)
        base.update({k: v for k, v in heur.items() if v is not None})
        guia = is_guia_arrecadacao(extracted_text, file_name)
        if guia:
            base = apply_guia_roles(base, extracted_text)
            warnings.append("Detected guia de arrecadação (tax slip); roles: payer vs tax authority.")
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
        is_guia=guia,
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
        if key == "amount":
            base[key] = _sanitize_amount_after_llm(value, pre_llm.get("amount"))
            continue
        base[key] = value

    if guia:
        base = apply_guia_roles(base, extracted_text)
        name_blob = f"{file_name or ''}\n{extracted_text}"
        only = re.sub(r"\D", "", extracted_text)
        if (
            BIKE_ANJO_CNPJ in only
            or re.search(r"(?is)bike[\s_-]*anjo|associa[cç][aã]o[\s_-]*bike", name_blob)
        ):
            base["payer_document"] = BIKE_ANJO_CNPJ
            if not base.get("payer_name"):
                base["payer_name"] = "ASSOCIACAO BIKE ANJO"

    # Hard rule: Bike Anjo must never remain as beneficiary.
    if base.get("beneficiary_document") == BIKE_ANJO_CNPJ or _name_looks_bike_anjo(base.get("beneficiary_name")):
        if not base.get("payer_document"):
            base["payer_document"] = BIKE_ANJO_CNPJ
        if not base.get("payer_name"):
            base["payer_name"] = "ASSOCIACAO BIKE ANJO"
        auth_name, _ = _guess_tax_authority(extracted_text)
        base["beneficiary_name"] = auth_name
        base["beneficiary_document"] = None
        warnings.append("Cleared Bike Anjo from beneficiary (taxpayer/payer on this document).")

    if (
        base.get("beneficiary_document")
        and base.get("payer_document")
        and base["beneficiary_document"] == base["payer_document"]
    ):
        warnings.append("Beneficiary and payer documents are identical; payer cleared.")
        base["payer_document"] = None

    # Prefer heuristic digitable/amount when LLM drops them.
    if pre_llm.get("digitable_line") and not base.get("digitable_line"):
        base["digitable_line"] = pre_llm["digitable_line"]
    if pre_llm.get("amount") is not None and base.get("amount") is None:
        base["amount"] = pre_llm["amount"]
    if pre_llm.get("document_number") and not base.get("document_number"):
        base["document_number"] = pre_llm["document_number"]

    if pre_llm.get("beneficiary_document") and base.get("beneficiary_document") != pre_llm["beneficiary_document"]:
        # Do not re-apply BA as beneficiary from heuristic.
        if pre_llm["beneficiary_document"] != BIKE_ANJO_CNPJ:
            warnings.append("LLM changed beneficiary document; kept heuristic value.")
            base["beneficiary_document"] = pre_llm["beneficiary_document"]
    # Do not reinstate a heuristic/LLM payer over a guia-corrected Bike Anjo payer.
    if (
        not guia
        and pre_llm.get("payer_document")
        and base.get("payer_document") != pre_llm.get("payer_document")
    ):
        if pre_llm["payer_document"]:
            base["payer_document"] = pre_llm["payer_document"]

    confidence_by_field = {
        k: _confidence_for_boleto_field(k, v, pre_llm) for k, v in base.items()
    }
    populated = sum(1 for s in confidence_by_field.values() if s > 0)
    result = {
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
    # Additive envelope (Bike Anjo clients read error.message first, then errors[0]).
    if errors:
        msg = errors[0] if isinstance(errors[0], str) else str(errors[0])
        result["error"] = {"code": "invalid_request", "message": msg}
    return result
