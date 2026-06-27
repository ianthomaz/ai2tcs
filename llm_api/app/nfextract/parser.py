"""NF parsing pipeline for XML/PDF/IMG extraction."""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from app.nfextract.llm_client import enrich_with_local_llm

# Strings the LLM sometimes returns instead of JSON null; orchestrators expect real null.
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


def _cnpj_checksum_valid(d14: str) -> bool:
    """True if 14-digit string passes Brazilian CNPJ check digits (rejects NFS-e key prefixes, etc.)."""
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


def _first_valid_cnpj_digits_from_text(compact: str) -> str | None:
    """First CNPJ-shaped match in reading order whose check digits are valid."""
    for raw in re.findall(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", compact):
        d = _digits(raw)
        if d and _cnpj_checksum_valid(d):
            return d
    return None


_PRESTADOR_BLOCK_RE = re.compile(
    r"(?is)PRESTADOR\s+DE\s+SERVI[ÇC]OS\s*(.*?)(?=TOMADOR\s+DE\s+SERVI[ÇC]OS)",
    re.DOTALL,
)
_TOMADOR_BLOCK_RE = re.compile(
    r"(?is)TOMADOR\s+DE\s+SERVI[ÇC]OS\s*(.*?)(?=DISCRIMINA[ÇC][AÃ]O|INTERMEDI[ÁA]RIO|VALOR\s+TOTAL|SERVI[ÇC]O\s+PRESTADO|$)",
    re.DOTALL,
)
_PRESTADOR_RAZAO_RE = re.compile(r"(?is)Nome/Raz\w*\s*Social[:\s]+([^\n]+?)(?:\s+Endere|$)")
_TOMADOR_RAZAO_RE = re.compile(r"(?is)Nome/Raz\w*\s*Social[:\s]+([^\n]+?)(?:\s+Endere|$)")
def _prestador_servicos_block(text: str) -> str | None:
    m = _PRESTADOR_BLOCK_RE.search(text)
    return m.group(1).strip() if m else None


def _tomador_servicos_block(text: str) -> str | None:
    m = _TOMADOR_BLOCK_RE.search(text)
    return m.group(1).strip() if m else None


def _tax_id_from_block(block: str) -> str | None:
    m = re.search(r"(?is)CPF/CNPJ[:\s]+([^\n]+)", block)
    if not m:
        return None
    line = m.group(1).strip()
    subm = re.search(r"(§?\d{1,2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})", line)
    if not subm:
        d = _digits(line)
        if d and len(d) in (11, 14):
            if len(d) == 14 and not _cnpj_checksum_valid(d):
                return None
            return d
        return None
    masked = subm.group(1)
    reference = _ocr_normalize_cnpj_line_for_reference(masked)
    candidates = _valid_cnpj_candidates_from_line(masked)
    picked = _pick_cnpj_closest_to_reference(candidates, reference)
    if picked:
        return picked
    d = _digits(masked)
    if d and len(d) == 11:
        return d
    return None


def _name_from_block(block: str, name_re: re.Pattern[str]) -> str | None:
    m = name_re.search(block)
    if not m:
        return None
    name = m.group(1).strip()
    name = re.sub(r"\s+", " ", name)
    return name or None


def _ocr_normalize_cnpj_line_for_reference(line: str) -> str:
    """Best-effort digit string from a noisy CNPJ line (OCR) for scoring candidates."""
    t = line
    t = t.replace("§3", "37").replace("§", "7")
    for a, b in (("O", "0"), ("o", "0"), ("D", "0"), ("I", "1"), ("l", "1"), ("|", "1")):
        t = t.replace(a, b)
    d = _digits(t)
    return d[:14] if d and len(d) >= 14 else (d or "")


def _valid_cnpj_candidates_from_line(line: str) -> list[str]:
    """Collect checksum-valid CNPJs from a single CPF/CNPJ value line (handles OCR gaps)."""
    found: list[str] = []
    seen: set[str] = set()

    def add(d: str | None) -> None:
        if d and len(d) == 14 and _cnpj_checksum_valid(d) and d not in seen:
            seen.add(d)
            found.append(d)

    cleaned = line.replace("§", "")
    for raw in re.findall(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", cleaned):
        add(_digits(raw))
    d0 = _digits(line)
    if d0 and len(d0) == 14:
        add(d0)
    if d0 and len(d0) == 13:
        for pos in range(14):
            for ch in "0123456789":
                cand = d0[:pos] + ch + d0[pos:]
                add(cand)
    return found


def _pick_cnpj_closest_to_reference(candidates: list[str], reference: str) -> str | None:
    if not candidates:
        return None
    if len(reference) == 14 and reference.isdigit():
        return min(candidates, key=lambda c: sum(1 for i in range(14) if c[i] != reference[i]))
    return candidates[0]


def _prestador_supplier_code(block: str) -> str | None:
    return _tax_id_from_block(block)


def _prestador_supplier_name(block: str) -> str | None:
    return _name_from_block(block, _PRESTADOR_RAZAO_RE)


def _extract_tomador_fields(text: str) -> tuple[dict[str, Any], bool]:
    """NFS-e PDF/OCR: tomador CNPJ/CPF before LLM enrichment."""
    out: dict[str, Any] = {}
    block = _tomador_servicos_block(text)
    if not block:
        return out, False
    code = _tax_id_from_block(block)
    if code:
        out["service_recipient_code"] = code
    name = _name_from_block(block, _TOMADOR_RAZAO_RE)
    if name:
        out["service_recipient_name"] = name
    return out, True


def _extract_prestador_supplier_fields(text: str) -> tuple[dict[str, Any], bool]:
    """NFS-e PDF/OCR: prestador CNPJ and legal name (avoids picking tomador CNPJ first)."""
    out: dict[str, Any] = {}
    block = _prestador_servicos_block(text)
    if not block:
        return out, False
    code = _prestador_supplier_code(block)
    if code:
        out["supplier_code"] = code
    name = _prestador_supplier_name(block)
    if name:
        out["supplier_name"] = name
    return out, True


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    normalized = value.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _xml_localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _find_text_by_localname(root: ET.Element, names: list[str]) -> str | None:
    names_set = set(names)
    for elem in root.iter():
        tag_name = _xml_localname(elem.tag)
        if tag_name in names_set and elem.text and elem.text.strip():
            return elem.text.strip()
    return None


def _xml_find_first_subtree(root: ET.Element, section_names: set[str]) -> ET.Element | None:
    for elem in root.iter():
        if _xml_localname(elem.tag) in section_names:
            return elem
    return None


def _xml_first_text_in_subtree(subtree: ET.Element, name_options: list[str]) -> str | None:
    want = set(name_options)
    for elem in subtree.iter():
        if _xml_localname(elem.tag) in want and elem.text and elem.text.strip():
            return elem.text.strip()
    return None


def _xml_tax_id_from_subtree(subtree: ET.Element) -> str | None:
    for elem in subtree.iter():
        ln = _xml_localname(elem.tag)
        if ln in ("CNPJ", "CPF", "Cnpj") and elem.text and elem.text.strip():
            return elem.text.strip()
        if ln == "CpfCnpj":
            for child in elem:
                cln = _xml_localname(child.tag)
                if cln in ("CNPJ", "CPF", "Cnpj") and child.text and child.text.strip():
                    return child.text.strip()
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
    prest = _xml_find_first_subtree(root, {"PrestadorServico", "Prestador", "emit"})
    tom = _xml_find_first_subtree(root, {"TomadorServico", "Tomador", "dest"})

    supplier_name: str | None = None
    supplier_cnpj_raw: str | None = None
    if prest is not None:
        supplier_name = _xml_first_text_in_subtree(prest, ["xNome", "RazaoSocial", "Nome"])
        supplier_cnpj_raw = _xml_tax_id_from_subtree(prest)
    if not supplier_name:
        supplier_name = _find_text_by_localname(root, ["xNome", "RazaoSocial"])
    if not supplier_cnpj_raw:
        supplier_cnpj_raw = _find_text_by_localname(root, ["CNPJ", "CpfCnpj"])

    service_recipient_raw: str | None = None
    if tom is not None:
        service_recipient_raw = _xml_tax_id_from_subtree(tom)

    nf_number = _find_text_by_localname(root, ["nNF", "Numero", "InfNfseNumero"])
    issue_date = _find_text_by_localname(root, ["dhEmi", "dEmi", "DataEmissao"])
    total = _find_text_by_localname(root, ["vNF", "ValorServicos", "ValorLiquidoNfse"])
    amount_tax = _find_text_by_localname(root, ["vISS", "ValorIss", "ValorIssRetido"])
    raw_text = ET.tostring(root, encoding="unicode")[:6000]
    data: dict[str, Any] = {
        "supplier_name": supplier_name,
        "supplier_code": _digits(supplier_cnpj_raw),
        "service_recipient_code": _digits(service_recipient_raw),
        "nf_number": nf_number,
        "issue_date": issue_date[:10] if issue_date else None,
        "amount": _to_float(total),
        "amount_tax": _to_float(amount_tax),
        "amount_type": "total",
    }
    if data.get("amount_tax"):
        data["amount_type"] = "imposto_retido"
        amt = data.get("amount")
        tax = data.get("amount_tax")
        if amt is not None and tax is not None and tax > 0 and amt > tax:
            data["amount_deposit"] = round(float(amt) - float(tax), 2)
    return data, raw_text


# PDFs that are only scanned images have no text layer; macOS Preview still allows
# selection via Live Text (OCR). Match that behavior when the layer is empty/too short.
_PDF_MEANINGFUL_TEXT_MIN_CHARS = 80
_PDF_OCR_MAX_PAGES = 3
_PDF_OCR_ZOOM = 2.0


def _extract_pdf_text(raw_bytes: bytes) -> str:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(io.BytesIO(raw_bytes))
    chunks: list[str] = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _extract_pdf_text_pymupdf(raw_bytes: bytes) -> str:
    try:
        import fitz  # type: ignore
    except Exception:
        return ""
    try:
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        try:
            parts: list[str] = []
            for i in range(len(doc)):
                parts.append(str(doc[i].get_text() or ""))
            return "\n".join(parts).strip()
        finally:
            doc.close()
    except Exception:
        return ""


def _extract_pdf_text_ocr_raster(raw_bytes: bytes, *, max_pages: int, zoom: float) -> str:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    try:
        import fitz  # type: ignore
    except Exception:
        return ""
    try:
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        try:
            mat = fitz.Matrix(zoom, zoom)
            chunks: list[str] = []
            for i in range(min(len(doc), max_pages)):
                pix = doc[i].get_pixmap(matrix=mat, alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                chunks.append(pytesseract.image_to_string(img, lang="por+eng"))
            return "\n\n".join(chunks).strip()
        finally:
            doc.close()
    except Exception:
        return ""


def extract_pdf_text_with_fallbacks(raw_bytes: bytes) -> tuple[str, list[str]]:
    """Prefer embedded text (pypdf, then PyMuPDF); if still too short, OCR rendered pages."""
    warnings: list[str] = []
    pypdf_text = _extract_pdf_text(raw_bytes)
    best = pypdf_text.strip()
    pymupdf_text = _extract_pdf_text_pymupdf(raw_bytes)
    if len(pymupdf_text.strip()) > len(best):
        best = pymupdf_text.strip()
    if len(best) >= _PDF_MEANINGFUL_TEXT_MIN_CHARS:
        return best, warnings
    ocr_text = _extract_pdf_text_ocr_raster(
        raw_bytes,
        max_pages=_PDF_OCR_MAX_PAGES,
        zoom=_PDF_OCR_ZOOM,
    ).strip()
    if len(ocr_text) > len(best):
        best = ocr_text
        warnings.append(
            "PDF had no usable text layer (or it was very short); applied OCR on rasterized pages."
        )
    elif len(best) < _PDF_MEANINGFUL_TEXT_MIN_CHARS and not ocr_text:
        warnings.append(
            "PDF text layer was very short and OCR produced no text "
            "(check Tesseract install and language packs por+eng)."
        )
    return best, warnings


def _extract_img_text(raw_bytes: bytes) -> str:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    image = Image.open(io.BytesIO(raw_bytes))
    return pytesseract.image_to_string(image, lang="por+eng")


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
    return max(parsed) if parsed else None


def _extract_nfs_e_discriminacao_clean(text: str) -> str | None:
    """Only the discrimination block (header + service lines), not totals or tax grid (NFS-e layout)."""
    m = re.search(r"(?is)discrimin\w*\s+dos\s+serv\w*", text)
    if not m:
        return None
    rest = text[m.start() :]
    endm = re.search(
        r"(?is)\n\s*(?:valor\s+total\s+do\s+servi[cço]|valor\s+total\s+da\s+nota|"
        r"outras\s+informa|\[\s*c[oód]igo\s+do\s+serv|inss\s*\(|pis\s*/|cofins\s*\(|"
        r"irrf\s*\(|csll\s*\(|municipio\s+da\s+prest)",
        rest,
    )
    chunk = rest[: endm.start()].strip() if endm else rest.strip()
    lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
    if not lines:
        return None
    content_lines: list[str] = []
    for ln in lines[1:]:
        low = ln.lower()
        if low.startswith("valor total") or "outras informa" in low:
            break
        if re.match(r"^\[?\s*c[oó]digo\s+do\s+serv", low):
            break
        if re.match(r"^(inss|pis|cofins|csll|irrf)\s*\(", low):
            break
        content_lines.append(ln)
        if len(content_lines) >= 4:
            break
    body = "\n".join(content_lines).strip()
    if not body:
        return None
    body = (
        body.replace("MBS", "MÊS")
        .replace("Mbs", "MÊS")
        .replace("mbs", "mês")
        .replace("NO MBS", "NO MÊS")
        .replace("No Mbs", "No mês")
    )
    if re.match(r"(?is)servicos\s+de\s+", body):
        body = "SERVIÇOS DE " + body[12:].lstrip()
    return f"DISCRIMINAÇÃO DOS SERVIÇOS\n{body}"


def _extract_description_section(text: str) -> str | None:
    disc = _extract_nfs_e_discriminacao_clean(text)
    if disc:
        return disc
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
        return cleaned[start : start + 800].strip()
    tail = cleaned[-800:].strip()
    return tail if tail else None


def _extract_payment_from_text(text: str) -> dict[str, Any]:
    compact = " ".join(text.split())
    lowered = compact.lower()
    pix_match = re.search(
        r"(?:pix[:\s-]*)([0-9A-Za-z@._+\-/]{8,}|"
        r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|"
        r"\d{3}\.?\d{3}\.?\d{3}-?\d{2})",
        compact,
        re.IGNORECASE,
    )
    bank_match = re.search(
        r"\b(banco\s+[a-zA-Z]+|santander|itau|itaú|bradesco|caixa|nubank|inter|sicredi|bb|banco do brasil)\b",
        lowered,
        re.IGNORECASE,
    )
    agency_match = re.search(r"\b(?:ag|ag[êe]ncia)\s*[:\-]?\s*(\d{3,6})\b", compact, re.IGNORECASE)
    account_match = re.search(r"\b(?:c\/?c|conta(?:\s*corrente)?)\s*[:\-]?\s*([\d.\-\/xX]{4,20})\b", compact, re.IGNORECASE)
    return {
        "payment_pixCode": pix_match.group(1).strip() if pix_match else None,
        "payment_bank": bank_match.group(1).upper() if bank_match else None,
        "payment_bank_agency": agency_match.group(1) if agency_match else None,
        "payment_bank_account": account_match.group(1) if account_match else None,
    }


def extract_from_text_heuristics(text: str) -> dict[str, Any]:
    compact = " ".join(text.split())
    prest_fields, prestador_block_found = _extract_prestador_supplier_fields(text)
    tomador_fields, tomador_block_found = _extract_tomador_fields(text)
    supplier_code = prest_fields.get("supplier_code")
    supplier_name = prest_fields.get("supplier_name")
    if supplier_code is None and not prestador_block_found:
        supplier_code = _first_valid_cnpj_digits_from_text(compact)
    nf_number_match = re.search(r"(?:nfs-e|nfse|nota fiscal)\D{0,30}(\d{1,8})", compact, re.IGNORECASE)
    if not nf_number_match:
        nf_number_match = re.search(r"(?:n[úu]mero)\D{0,8}(\d{1,8})", compact, re.IGNORECASE)
    amount = _extract_total_amount(compact)
    data: dict[str, Any] = {
        "supplier_code": supplier_code,
        "supplier_name": supplier_name,
        "service_recipient_code": tomador_fields.get("service_recipient_code"),
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


_MONTH_PT = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _issue_date_prefix_line(issue_date: str | None) -> str | None:
    if not issue_date or not isinstance(issue_date, str):
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", issue_date.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"NF emitida {d:02d}/{_MONTH_PT[mo - 1]}/{y}"


_VALID_PAYMENT_TYPES = frozenset({"pix", "boleto", "transferencia", "cartao_credito", "dinheiro"})


def _normalize_payment_type_field(value: Any) -> str | None:
    v = _normalize_nf_llm_value(value)
    if not isinstance(v, str):
        return None
    s = v.strip().lower()
    return s if s in _VALID_PAYMENT_TYPES else None


def _infer_payment_type_from_fields(base: dict[str, Any], extracted_text: str) -> str | None:
    pix = base.get("payment_pixCode")
    if isinstance(pix, str) and pix.strip():
        return "pix"
    low = extracted_text.lower()
    if "boleto" in low or "linha digitável" in low or "linha digitavel" in low:
        return "boleto"
    if "cartão de crédito" in low or "cartao de credito" in low:
        return "cartao_credito"
    if "dinheiro" in low or "espécie" in low or "especie" in low:
        return "dinheiro"
    if "codigo de barras" in low or "código de barras" in low:
        return "boleto"
    if any(base.get(k) for k in ("payment_bank", "payment_bank_agency", "payment_bank_account")):
        return "transferencia"
    return None


def _normalize_service_recipient_digits(value: Any) -> str | None:
    v = _normalize_nf_llm_value(value)
    if not isinstance(v, str):
        return None
    d = re.sub(r"\D", "", v)
    if len(d) == 14:
        return d if _cnpj_checksum_valid(d) else None
    if len(d) == 11:
        return d
    return None


def _sanitize_service_recipient_value(raw: Any) -> str | None:
    if raw is None:
        return None
    d = _digits(str(raw))
    if not d:
        return None
    if len(d) == 14:
        return d if _cnpj_checksum_valid(d) else None
    if len(d) == 11:
        return d
    return None


def apply_nf_extract_postprocess(base: dict[str, Any], extracted_text: str) -> None:
    """Infer payment_type, normalize description prefix from issue_date, sanitize tax ids."""
    base["service_recipient_code"] = _sanitize_service_recipient_value(base.get("service_recipient_code"))

    pt = _normalize_payment_type_field(base.get("payment_type"))
    if pt is None:
        pt = _infer_payment_type_from_fields(base, extracted_text)
    base["payment_type"] = pt

    desc = base.get("description")
    if isinstance(desc, str) and desc.strip():
        s = desc.strip()
        if s.lower().startswith("nf emitida"):
            base["description"] = s
        else:
            prefix = _issue_date_prefix_line(base.get("issue_date"))
            if prefix:
                base["description"] = f"{prefix}\n{s}"

    if base.get("amount_type") == "unknown" and base.get("amount") is not None:
        base["amount_type"] = "total"


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


def _validate_role_documents(
    base: dict[str, Any],
    heuristic_snapshot: dict[str, Any],
    warnings: list[str],
) -> None:
    """Prevent LLM from swapping prestador/tomador tax ids when heuristics found both."""
    h_sup = heuristic_snapshot.get("supplier_code")
    h_rec = heuristic_snapshot.get("service_recipient_code")
    if h_sup and h_rec and h_sup == h_rec:
        warnings.append("Heuristic prestador and tomador share the same document; tomador cleared.")
        base["service_recipient_code"] = None
        return
    if h_sup and base.get("supplier_code") == h_rec and base.get("service_recipient_code") == h_sup:
        warnings.append("LLM swapped prestador/tomador documents; restored heuristic values.")
        base["supplier_code"] = h_sup
        base["service_recipient_code"] = h_rec
        return
    if h_sup and base.get("supplier_code") != h_sup:
        warnings.append("LLM changed prestador document; kept heuristic prestador value.")
        base["supplier_code"] = h_sup
    if h_rec and base.get("service_recipient_code") != h_rec:
        warnings.append("LLM changed tomador document; kept heuristic tomador value.")
        base["service_recipient_code"] = h_rec
    if (
        base.get("supplier_code")
        and base.get("service_recipient_code")
        and base["supplier_code"] == base["service_recipient_code"]
    ):
        warnings.append("Prestador and tomador documents are identical after merge; tomador cleared.")
        base["service_recipient_code"] = None


def _confidence_for_field(
    field: str,
    value: Any,
    heuristic_snapshot: dict[str, Any],
    llm_touched: set[str],
    conflict_fields: set[str],
) -> float:
    if value in (None, "", "unknown"):
        return 0.0
    if field in conflict_fields:
        return 0.4
    if field in heuristic_snapshot and heuristic_snapshot[field] == value:
        return 0.9
    if field in llm_touched:
        return 0.6
    return 0.75


async def run_extraction_pipeline(
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
        "service_recipient_code": None,
        "payment_type": None,
    }
    extracted_text = ""
    heuristic_snapshot: dict[str, Any] = {}
    try:
        if doc_type == "xml":
            xml_data, extracted_text = extract_from_xml(raw_bytes)
            base.update({k: v for k, v in xml_data.items() if v is not None})
            heuristic_snapshot = {
                k: base[k]
                for k in ("supplier_code", "supplier_name", "service_recipient_code")
                if base.get(k) not in (None, "", "unknown")
            }
        elif doc_type == "pdf":
            extracted_text, pdf_warnings = extract_pdf_text_with_fallbacks(raw_bytes)
            warnings.extend(pdf_warnings)
            heur = extract_from_text_heuristics(extracted_text)
            base.update({k: v for k, v in heur.items() if v is not None})
            heuristic_snapshot = {
                k: heur[k]
                for k in ("supplier_code", "supplier_name", "service_recipient_code")
                if heur.get(k) not in (None, "", "unknown")
            }
        elif doc_type == "img":
            extracted_text = _extract_img_text(raw_bytes)
            heur = extract_from_text_heuristics(extracted_text)
            base.update({k: v for k, v in heur.items() if v is not None})
            heuristic_snapshot = {
                k: heur[k]
                for k in ("supplier_code", "supplier_name", "service_recipient_code")
                if heur.get(k) not in (None, "", "unknown")
            }
        else:
            errors.append("Unsupported document type. Send XML, PDF, or image.")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    pre_llm = dict(base)
    llm_data, llm_warnings = await enrich_with_local_llm(
        ollama_host=ollama_host,
        model=ollama_model,
        base_data=base,
        extracted_text=extracted_text,
        timeout_s=ollama_timeout_s,
    )
    warnings.extend(llm_warnings)
    llm_touched: set[str] = set()
    for key, value in llm_data.items():
        if key not in base:
            continue
        if key == "service_recipient_code":
            normalized = _normalize_service_recipient_digits(value)
            if normalized and normalized != pre_llm.get(key):
                llm_touched.add(key)
            if normalized:
                base[key] = normalized
            continue
        if key == "payment_type":
            normalized = _normalize_payment_type_field(value)
            if normalized and normalized != pre_llm.get(key):
                llm_touched.add(key)
            if normalized:
                base[key] = normalized
            continue
        normalized = _normalize_nf_llm_value(value)
        if normalized not in ("", None):
            if normalized != pre_llm.get(key):
                llm_touched.add(key)
            base[key] = normalized
    conflict_before = len(warnings)
    _validate_role_documents(base, heuristic_snapshot, warnings)
    conflict_fields = set()
    if len(warnings) > conflict_before:
        conflict_fields = {"supplier_code", "service_recipient_code"}
    apply_nf_extract_postprocess(base, extracted_text)
    confidence_by_field: dict[str, float] = {}
    populated = 0
    for k, v in base.items():
        score = _confidence_for_field(k, v, heuristic_snapshot, llm_touched, conflict_fields)
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
