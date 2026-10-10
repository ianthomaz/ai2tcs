"""Shared plumbing for the Bike Anjo ops ports: access gate, envelope, contract files, JSON chat.

Contract (source of truth): contracts/bikeanjo/ — copied from bikeanjo2026all, see ORIGIN.md.
Envelope: success is {"status": "ok", ..., "model", "prompt_version", "warnings"}; a content
error is HTTP 200 with {"status": "error", "error": {"code", "message"}} (common.schema.json).
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request

from app.auth import require_token
from app.config import settings
from app.tasks import engine
from app.tasks.engine import (  # noqa: F401 — re-exported for the Bike Anjo ports
    PortError,
    clamp_confidence,
    compact_json,
    error_body,
    parse_json_object,
    read_request,
)

logger = logging.getLogger(__name__)

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts" / "bikeanjo"

__all__ = [
    "PortError",
    "clamp_confidence",
    "compact_json",
    "error_body",
    "parse_json_object",
    "read_request",
]


async def require_bikeanjo_project(request: Request, _: None = Depends(require_token)) -> str:
    """Only the Bike Anjo project key gets in; returns the project_id the call runs under.

    require_token already rejected missing/invalid tokens (401). The global token and a
    key of any other project get 403 — the ports are not a shared surface of the ai2tcs.
    """
    scoped = getattr(request.state, "project_id", None)
    if isinstance(scoped, str) and scoped in settings.bikeanjo_ops_project_id_set():
        return scoped
    raise HTTPException(status_code=403, detail="Bike Anjo ports require the Bike Anjo project key")


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


async def chat_json(
    project: dict | None,
    *,
    system: str,
    user: str,
    validate: Callable[[dict[str, Any]], list[str]] | None = None,
    attempts: int = 2,
) -> tuple[dict[str, Any], str]:
    """The task engine's chat_json with the Bike Anjo ports' budget (BIKEANJO_OPS_*)."""
    return await engine.chat_json(
        project,
        system=system,
        user=user,
        validate=validate,
        attempts=attempts,
        kind="bikeanjo_ops",
        model_alias=settings.bikeanjo_ops_model_alias,
        timeout_s=settings.bikeanjo_ops_timeout_s,
        num_predict=settings.bikeanjo_ops_num_predict,
        temperature=settings.bikeanjo_ops_temperature,
    )


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
        # Fall with injury and no help (triage-v2 rule 1): calm tone does not lower it.
        r"\bmachuc(ou|ei|ada|ado|aram)\b",
        r"\bvirei o pe\b",
        r"\btorc(i|eu) o (pe|tornozelo|joelho|pulso|braco)",
        r"\b(fratur|luxa|tor[cç]ao)",
        r"\bnem (me )?ajudou a levantar",
        r"\bninguem (veio )?(me |a |o )?(ajudar|socorr)",
        r"\bdificuldades? (pra|para) andar\b",
    )
)


def grave_hits(*texts: str) -> list[str]:
    folded = " \n ".join(fold(t) for t in texts if t)
    return [p.pattern for p in GRAVE_PATTERNS if p.search(folded)]
