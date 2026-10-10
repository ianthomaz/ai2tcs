"""POST /extract and POST /extract-multi — zapzap onboarding (sync Ollama)."""
import asyncio
import json
import re
from datetime import datetime

import ollama

from fastapi import APIRouter, Depends, Request

from app.auth import require_token
from app.config import settings
from app.job_audit import log_sync_llm_job
from app.models import ExtractMultiRequest, ExtractMultiResponse, ExtractRequest, ExtractResponse
from app.registry import get_extract_steps_config, get_project

router = APIRouter(tags=["extract"])

EXTRACT_JOB_KIND = "extract"
EXTRACT_MULTI_JOB_KIND = "extract_multi"

# Instructions per step so the LLM returns a value that zapzap validators accept.
STEP_INSTRUCTIONS = {
    "interesse": "Return only the number 1-6 (1=Aprender a pedalar, 2=Dicas rotas, 3=Comprar bicicleta, 4=Bike parada, 5=Oferecer ajuda, 6=Outros). If unclear, return NULL.",
    "nome": "Return only the person's full name, nothing else. If no name found, return NULL.",
    "cpf": "Return only 11 digits (numbers only, no dots or dashes). If not found or invalid, return NULL.",
    "email": "Return only a valid email address. If not found, return NULL.",
    "nascimento": "Return only the birth date as dd/mm/yyyy (e.g. 15/03/1990). If not found or invalid, return NULL.",
    "cep": "Return only 8 digits (Brazilian postal code). If not found or invalid, return NULL.",
    "reply_intent": "Return only one code from the list in the Question, exactly as written (lowercase, with underscores). If you are not sure, return none.",
}

PAYMENT_BOLETO_ALLOWED_KEYS = frozenset(
    {
        "beneficiary_name",
        "beneficiary_document",
        "payer_name",
        "payer_document",
        "digitable_line",
        "barcode",
        "due_date",
        "amount",
        "bank_code",
        "document_number",
        "payment_type",
        "notes",
    }
)


def _normalize_email_value(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s or "@" not in s:
        return None
    return s if re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", s) else None


def _normalize_nascimento(raw: str) -> str | None:
    """Normalize to dd/mm/yyyy for zapzap validators."""
    s = (raw or "").strip()
    if not s:
        return None
    s = re.sub(r"^(nascimento|data)\s*:\s*", "", s, flags=re.IGNORECASE).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(s[:10] if len(s) >= 10 else s, fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", s):
        return s
    return None


# reply_intent: the question lists the allowed codes, one per line as "- code: meaning"
# (zapzap/lib/reply-reader.js buildLlmQuestion) or inline as "Codes: a, b, c".
_REPLY_INTENT_LINE = re.compile(r"^\s*-\s*([a-z0-9_]+)\s*:", re.MULTILINE)
_REPLY_INTENT_INLINE = re.compile(r"codes?\s*:\s*([a-z0-9_,\s]+)", re.IGNORECASE)
_REPLY_INTENT_TOKEN = re.compile(r"[a-z0-9_]+")


def reply_intent_codes(question: str) -> list[str]:
    """Codes the question allows, plus `none`. Empty when the question lists none."""
    codes = _REPLY_INTENT_LINE.findall(question or "")
    if not codes:
        m = _REPLY_INTENT_INLINE.search(question or "")
        if m:
            codes = [c.strip().lower() for c in m.group(1).split(",") if c.strip()]
    if not codes:
        return []
    return list(dict.fromkeys([*codes, "none"]))


def normalize_reply_intent(raw: str, question: str) -> str | None:
    """First code-shaped token of the answer, kept only when the question allows it."""
    token = _REPLY_INTENT_TOKEN.search((raw or "").strip().lower())
    if not token:
        return None
    code = token.group(0)
    allowed = reply_intent_codes(question)
    if allowed and code not in allowed:
        return None
    return code


def _normalize_extracted(step: str, raw: str) -> str | None:
    """Clean LLM output so it passes zapzap validators."""
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    if raw.upper() == "NULL" or raw.lower() == "não" or raw.lower() == "nao":
        return None
    # Remove common LLM wrappers
    raw = re.sub(r"^(resposta|valor|extraído|extracted):\s*", "", raw, flags=re.IGNORECASE).strip()
    if step == "cep":
        digits = re.sub(r"\D", "", raw)
        return digits if len(digits) == 8 else None
    if step == "cpf":
        digits = re.sub(r"\D", "", raw)
        return digits if len(digits) == 11 else None
    if step == "email":
        return _normalize_email_value(raw)
    if step == "nascimento":
        return _normalize_nascimento(raw)
    if step == "nome":
        name = raw.strip()
        return name if len(name) >= 2 else None
    if step == "interesse":
        raw_lower = raw.lower().strip()
        if raw_lower in ("1", "2", "3", "4", "5", "6"):
            return raw
        mapping = {
            "aprender a pedalar": "1",
            "pedalar": "1",
            "rotas": "2",
            "comprar": "3",
            "bike parada": "4",
            "manutenção": "4",
            "oferecer ajuda": "5",
            "outros": "6",
        }
        for k, v in mapping.items():
            if k in raw_lower:
                return v
        return None
    return raw if len(raw) >= 1 else None


def _parse_llm_json_object(content: str) -> dict:
    """Best-effort JSON object from model output."""
    text = (content or "").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        out = json.loads(m.group())
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        return {}


def _sanitize_payment_boleto_object(parsed: dict) -> str:
    if not parsed or not isinstance(parsed, dict):
        return "{}"
    clean: dict[str, str] = {}
    for k, v in parsed.items():
        kid = str(k).strip().lower()
        if kid not in PAYMENT_BOLETO_ALLOWED_KEYS:
            continue
        if v is None:
            continue
        s = str(v).strip()
        if kid in ("beneficiary_document", "payer_document", "digitable_line", "barcode"):
            s = re.sub(r"\D", "", s)
        if not s or s.upper() == "NULL":
            continue
        clean[kid] = s
    return json.dumps(clean, ensure_ascii=False)


async def _project_extract_system(request: ExtractRequest, step: str, default: str) -> str:
    if not request.project_id:
        return default
    project = await get_project(request.project_id)
    if not project:
        return default
    steps_cfg = get_extract_steps_config(project)
    step_cfg = steps_cfg.get(step) if isinstance(steps_cfg, dict) else None
    if isinstance(step_cfg, dict):
        custom = step_cfg.get("system_instruction")
        if isinstance(custom, str) and custom.strip():
            return custom.strip()
    return default


async def _extract_payment_boleto_confirmation(req: Request, request: ExtractRequest) -> ExtractResponse:
    """Zapzap payment flow: free-text corrections after boleto read → JSON object string."""
    system = await _project_extract_system(
        request,
        "payment_boleto_confirmation",
        (
            "You extract structured corrections for a Brazilian bank slip (boleto). "
            "Reply with ONE JSON object only, no markdown. "
            "beneficiary_document = CNPJ/CPF of cedente/beneficiário (who receives). "
            "payer_document = CNPJ/CPF of sacado/pagador (who pays). Never swap them. "
            "Allowed keys: beneficiary_name, beneficiary_document, payer_name, payer_document, "
            "digitable_line, barcode, due_date, amount, bank_code, document_number, payment_type, notes. "
            "payment_type must be boleto when applicable. "
            "Omit keys you cannot infer. If nothing applies, return exactly {}."
        ),
    )
    user_content = f"Server context:\n{request.question}\n\nUser message:\n{request.user_reply}\n"
    model_alias = settings.get_model_name(request.model, default_alias="smart")
    try:
        response = await asyncio.to_thread(
            ollama.chat,
            model=model_alias,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            options={"temperature": 0.1, "num_predict": 900},
        )
        content = (response.get("message") or {}).get("content") or ""
        parsed = _parse_llm_json_object(content)
        out = ExtractResponse(extracted=_sanitize_payment_boleto_object(parsed))
        await log_sync_llm_job(
            req,
            project_id_explicit=request.project_id,
            job_kind=EXTRACT_JOB_KIND,
            question=f"extract:payment_boleto_confirmation\n{request.user_reply[:8000]}",
            status="done",
            model_alias=model_alias,
            answer=out,
            user_context={"endpoint": "/extract", "step": "payment_boleto_confirmation"},
        )
        return out
    except Exception:
        out = ExtractResponse(extracted=None)
        await log_sync_llm_job(
            req,
            project_id_explicit=request.project_id,
            job_kind=EXTRACT_JOB_KIND,
            question=f"extract:payment_boleto_confirmation\n{request.user_reply[:8000]}",
            status="failed",
            model_alias=model_alias,
            answer=out,
            error_message="ollama_or_parse_failed",
            user_context={"endpoint": "/extract", "step": "payment_boleto_confirmation"},
        )
        return out


def _normalize_field_value(field_id: str, raw: object) -> str | None:
    if raw is None or (isinstance(raw, str) and raw.lower() in ("null", "none", "")):
        return None
    fid = field_id.strip().lower()
    if fid == "contact_email":
        return _normalize_email_value(str(raw))
    return _normalize_extracted(fid, str(raw))


@router.post("/extract-multi", response_model=ExtractMultiResponse)
async def extract_multi(req: Request, request: ExtractMultiRequest, _: None = Depends(require_token)):
    """Extract several onboarding fields from one user message (zapzap contract)."""
    field_ids = [f.id.strip().lower() for f in request.fields]
    lines = []
    for f in request.fields:
        lines.append(f"- id={f.id}: {f.label} (example: {f.example})")
    fields_block = "\n".join(lines)
    ctx_block = "{}"
    if request.context:
        ctx_block = json.dumps(
            request.context.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
        )

    system = (
        "You extract structured fields from a WhatsApp user message (onboarding or payment-request corrections). "
        "Reply with ONE JSON object only. Keys must be a subset of these ids: "
        f"{field_ids}. "
        "Use string values only; omit keys you cannot extract confidently. "
        "Do not wrap in markdown."
    )
    user_content = (
        f"User message:\n{request.user_reply}\n\n"
        f"Fields to try:\n{fields_block}\n\n"
        f"Context JSON:\n{ctx_block}"
    )

    num_predict = 900 if len(field_ids) > 8 else 512

    model_alias = settings.get_model_name(request.model, default_alias="fast")
    try:
        response = await asyncio.to_thread(
            ollama.chat,
            model=model_alias,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            options={"temperature": 0.1, "num_predict": num_predict},
        )
        content = (response.get("message") or {}).get("content") or ""
    except Exception:
        out = ExtractMultiResponse(extracted={})
        await log_sync_llm_job(
            req,
            project_id_explicit=request.project_id,
            job_kind=EXTRACT_MULTI_JOB_KIND,
            question=request.user_reply[:12000],
            status="failed",
            model_alias=model_alias,
            answer=out,
            error_message="ollama_failed",
            user_context={"endpoint": "/extract-multi", "field_ids": field_ids},
        )
        return out

    parsed = _parse_llm_json_object(content)
    allowed = set(field_ids)
    out: dict[str, str] = {}
    for key, val in parsed.items():
        kid = str(key).strip().lower()
        if kid not in allowed:
            continue
        norm = _normalize_field_value(kid, val)
        if norm is not None:
            out[kid] = norm
    resp = ExtractMultiResponse(extracted=out)
    await log_sync_llm_job(
        req,
        project_id_explicit=request.project_id,
        job_kind=EXTRACT_MULTI_JOB_KIND,
        question=request.user_reply[:12000],
        status="done",
        model_alias=model_alias,
        answer=resp,
        user_context={"endpoint": "/extract-multi", "field_ids": field_ids},
    )
    return resp


@router.post("/extract", response_model=ExtractResponse)
async def extract(req: Request, request: ExtractRequest, _: None = Depends(require_token)):
    """Synchronous extract: one Ollama call, return { extracted: value } or { extracted: null }."""
    step = (request.step or "").strip().lower()
    if step == "payment_boleto_confirmation":
        return await _extract_payment_boleto_confirmation(req, request)

    instruction = STEP_INSTRUCTIONS.get(step)
    model_alias = settings.get_model_name(request.model, default_alias="fast")
    if not instruction:
        out = ExtractResponse(extracted=None)
        await log_sync_llm_job(
            req,
            project_id_explicit=request.project_id,
            job_kind=EXTRACT_JOB_KIND,
            question=f"extract:{step}\n{request.user_reply[:8000]}",
            status="done",
            model_alias=model_alias,
            answer=out,
            user_context={"endpoint": "/extract", "step": step, "note": "unknown_step"},
        )
        return out

    system = (
        "You extract a single value from the user's reply to a form question. "
        "Reply with ONLY the extracted value, or the word NULL if you cannot extract it. "
        "No explanation, no punctuation around the value."
    )
    user_content = (
        f"Question: {request.question}\n\n"
        f"User reply: {request.user_reply}\n\n"
        f"Rule: {instruction}"
    )

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                ollama.chat,
                model=model_alias,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                options={"temperature": 0.1, "num_predict": 64},
            ),
            timeout=settings.extract_timeout_s,
        )
        content = (response.get("message") or {}).get("content") or ""
        if step == "reply_intent":
            value = normalize_reply_intent(content, request.question)
        else:
            value = _normalize_extracted(step, content)
        out = ExtractResponse(extracted=value)
        await log_sync_llm_job(
            req,
            project_id_explicit=request.project_id,
            job_kind=EXTRACT_JOB_KIND,
            question=f"extract:{step}\n{request.user_reply[:8000]}",
            status="done",
            model_alias=model_alias,
            answer=out,
            user_context={"endpoint": "/extract", "step": step},
        )
        return out
    except Exception:
        out = ExtractResponse(extracted=None)
        await log_sync_llm_job(
            req,
            project_id_explicit=request.project_id,
            job_kind=EXTRACT_JOB_KIND,
            question=f"extract:{step}\n{request.user_reply[:8000]}",
            status="failed",
            model_alias=model_alias,
            answer=out,
            error_message="ollama_failed",
            user_context={"endpoint": "/extract", "step": step},
        )
        return out
