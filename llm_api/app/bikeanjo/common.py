"""Shared plumbing for the Bike Anjo ops ports: access gate, envelope, contract files, JSON chat.

Contract (source of truth): contracts/bikeanjo/ — copied from bikeanjo2026all, see ORIGIN.md.
Envelope: success is {"status": "ok", ..., "model", "prompt_version", "warnings"}; a content
error is HTTP 200 with {"status": "error", "error": {"code", "message"}} (common.schema.json).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ValidationError

from app.auth import require_token, security
from app.config import settings
from app.llm import get_provider

logger = logging.getLogger(__name__)

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts" / "bikeanjo"

ErrorCode = Literal["invalid_request", "timeout", "model_error", "unauthorized"]


class PortError(Exception):
    """Content-level failure, answered as HTTP 200 with the common error envelope."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def error_body(code: ErrorCode, message: str) -> dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message}}


async def require_bikeanjo_project(
    request: Request,
    _: None = Depends(require_token),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Only Bike Anjo may call these ports: its scoped key, or the operator's global token.

    require_token already rejected missing/invalid tokens (401). Here a valid key of any
    other project gets 403 — the ports are not a shared surface of the ai2tcs.
    Returns the project_id the call runs under.
    """
    allowed = settings.bikeanjo_ops_project_id_set()
    scoped = getattr(request.state, "project_id", None)
    if isinstance(scoped, str) and scoped:
        if scoped in allowed:
            return scoped
        raise HTTPException(status_code=403, detail="API key not authorized for Bike Anjo ports")

    is_global = bool(
        credentials
        and settings.llm_api_token
        and credentials.credentials == settings.llm_api_token
    )
    if is_global and settings.bikeanjo_ops_allow_global_token and allowed:
        return sorted(allowed)[0]
    raise HTTPException(status_code=403, detail="Bike Anjo ports require the Bike Anjo project key")


async def read_request(request: Request, model: type[BaseModel]) -> BaseModel:
    """Parse the JSON body into `model`; unknown fields are ignored (models use extra='ignore')."""
    try:
        raw = await request.json()
    except Exception:
        raise PortError("invalid_request", "O corpo precisa ser JSON.")
    if not isinstance(raw, dict):
        raise PortError("invalid_request", "O corpo precisa ser um objeto JSON.")
    try:
        return model.model_validate(raw)
    except ValidationError as e:
        first = e.errors()[0] if e.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ())) or "body"
        raise PortError("invalid_request", f"Campo inválido: {where} — {first.get('msg', 'inválido')}")


# ---------------------------------------------------------------- contract files


@lru_cache(maxsize=None)
def load_prompt(file_name: str) -> str:
    """System prompt body from contracts/bikeanjo/prompts/: everything after the first `---` rule.

    The lines above the rule are notes for whoever pastes the prompt, not for the model.
    """
    text = (CONTRACTS_DIR / "prompts" / file_name).read_text(encoding="utf-8")
    parts = re.split(r"^---\s*$", text, maxsplit=1, flags=re.MULTILINE)
    return (parts[1] if len(parts) == 2 else text).strip()


@lru_cache(maxsize=None)
def load_retrieval_hints() -> dict[str, Any]:
    return json.loads((CONTRACTS_DIR / "rag" / "retrieval-hints.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- model call


def parse_json_object(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        out = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


async def chat_json(
    project: dict | None,
    *,
    system: str,
    user: str,
    validate: Callable[[dict[str, Any]], list[str]] | None = None,
    attempts: int = 2,
) -> tuple[dict[str, Any], str]:
    """One JSON object from the project's provider. Returns (object, model name).

    `validate` lists what is missing in the object; a non-empty list asks the model again,
    with the list as the repair hint. Raises PortError("timeout") when the model does not
    answer within the port budget and PortError("model_error") when it fails or keeps
    answering something unusable.
    """
    model_name = settings.get_model_name(settings.bikeanjo_ops_model_alias, default_alias="smart")
    provider = get_provider(project or {})
    options = {
        "temperature": settings.bikeanjo_ops_temperature,
        "num_predict": settings.bikeanjo_ops_num_predict,
        "format": "json",
    }
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(attempts):
        try:
            content = await asyncio.wait_for(
                provider.chat(model=model_name, messages=messages, options=options),
                timeout=settings.bikeanjo_ops_timeout_s,
            )
        except asyncio.TimeoutError:
            raise PortError("timeout", f"O modelo não respondeu em {settings.bikeanjo_ops_timeout_s:.0f}s.")
        except Exception as e:
            logger.warning("bikeanjo ops chat failed: %s", e)
            raise PortError("model_error", "Falha ao chamar o modelo.")
        parsed = parse_json_object(content)
        problems = ["a resposta não é um objeto JSON"] if parsed is None else (validate(parsed) if validate else [])
        if parsed is not None and not problems:
            return parsed, model_name
        logger.info("bikeanjo ops: unusable answer (attempt %d): %s", attempt + 1, problems)
        messages = messages + [
            {"role": "assistant", "content": content[:2000]},
            {
                "role": "user",
                "content": "Corrija e responda de novo com UM objeto JSON válido e nada mais. Problemas: "
                + "; ".join(problems),
            },
        ]
    raise PortError("model_error", "O modelo não devolveu JSON válido: " + "; ".join(problems))


def compact_json(payload: Any) -> str:
    """Model input without indentation: the same data in fewer tokens."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def clamp_confidence(raw: object) -> float:
    try:
        v = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return max(0.0, min(1.0, v))


def fold(text: str) -> str:
    """Lowercase, accents removed, whitespace collapsed — for substring checks only."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().lower()


# Harassment, violence, threat, harm to a person. Matched on fold(text): no accents, lowercase.
# Recall over precision — a hit is a flag for a person to read, never a verdict.
GRAVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\bassedi",
        r"\babus(o|ad|ou)",
        r"\bestupr",
        r"\bagred(i|iu|ir)",
        r"\bagressao",
        r"sobre o? ?meu corpo",
        r"passou a mao",
        r"\bsangr",
        r"\bracis",
        r"\bhomofob",
        r"\btransfob",
        r"\bme ameac",
        r"\bameac(ou|aram|a de morte)",
        r"\bquebro tudo",
        r"\bvou (te |ai e )?(matar|bater|quebrar)",
    )
)


def grave_hits(*texts: str) -> list[str]:
    folded = " \n ".join(fold(t) for t in texts if t)
    return [p.pattern for p in GRAVE_PATTERNS if p.search(folded)]
