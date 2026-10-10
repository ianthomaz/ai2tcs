"""Engine shared by every text task: request reading, error envelope, one JSON object from the model.

Envelope: success is {"status": "ok", ..., "model", "prompt_version", "warnings"}; a content
error is HTTP 200 with {"status": "error", "error": {"code", "message"}}. Transport errors
(401/403/5xx) stay HTTP.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Literal

from fastapi import Request
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.llm import get_provider
from app.llm import metrics as llm_metrics
from app.registry import get_num_ctx

logger = logging.getLogger(__name__)

ErrorCode = Literal["invalid_request", "timeout", "model_error", "unauthorized"]


class PortError(Exception):
    """Content-level failure, answered as HTTP 200 with the error envelope."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def error_body(code: ErrorCode, message: str) -> dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message}}


async def read_json_object(request: Request) -> dict[str, Any]:
    try:
        raw = await request.json()
    except Exception:
        raise PortError("invalid_request", "O corpo precisa ser JSON.")
    if not isinstance(raw, dict):
        raise PortError("invalid_request", "O corpo precisa ser um objeto JSON.")
    return raw


async def read_request(request: Request, model: type[BaseModel]) -> BaseModel:
    """Parse the JSON body into `model`; unknown fields are ignored (models use extra='ignore')."""
    raw = await read_json_object(request)
    try:
        return model.model_validate(raw)
    except ValidationError as e:
        first = e.errors()[0] if e.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ())) or "body"
        raise PortError("invalid_request", f"Campo inválido: {where} — {first.get('msg', 'inválido')}")


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
    kind: str = "task",
    model_alias: str | None = None,
    timeout_s: float | None = None,
    num_predict: int | None = None,
    temperature: float | None = None,
) -> tuple[dict[str, Any], str]:
    """One JSON object from the project's provider. Returns (object, model name).

    `validate` lists what is missing in the object; a non-empty list asks the model again,
    with the list as the repair hint. Raises PortError("timeout") when the model does not
    answer within the budget and PortError("model_error") when it fails or keeps answering
    something unusable. Defaults: TASK_MODEL_ALIAS, TASK_TIMEOUT_S, TASK_NUM_PREDICT,
    TASK_TEMPERATURE.
    """
    model_name = settings.get_model_name(model_alias or settings.task_model_alias, default_alias="smart")
    timeout = timeout_s if timeout_s is not None else settings.task_timeout_s
    provider = get_provider(project or {})
    num_ctx = get_num_ctx(project)
    options = {
        "temperature": temperature if temperature is not None else settings.task_temperature,
        "num_predict": num_predict if num_predict is not None else settings.task_num_predict,
        "format": "json",
        **({"num_ctx": num_ctx} if num_ctx else {}),
    }
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    problems: list[str] = []
    for attempt in range(attempts):
        try:
            call = getattr(provider, "chat_with_metrics", None)
            if call is not None:
                content, call_metrics = await asyncio.wait_for(
                    call(model=model_name, messages=messages, options=options), timeout=timeout
                )
                llm_metrics.record(kind, (project or {}).get("project_id"), model_name, call_metrics, num_ctx)
            else:
                content = await asyncio.wait_for(
                    provider.chat(model=model_name, messages=messages, options=options), timeout=timeout
                )
        except asyncio.TimeoutError:
            raise PortError("timeout", f"O modelo não respondeu em {timeout:.0f}s.")
        except Exception as e:
            logger.warning("%s chat failed: %s", kind, e)
            raise PortError("model_error", "Falha ao chamar o modelo.")
        parsed = parse_json_object(content)
        problems = ["a resposta não é um objeto JSON"] if parsed is None else (validate(parsed) if validate else [])
        if parsed is not None and not problems:
            return parsed, model_name
        logger.info("%s: unusable answer (attempt %d): %s", kind, attempt + 1, problems)
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
