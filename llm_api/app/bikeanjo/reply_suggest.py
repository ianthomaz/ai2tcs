"""POST /replySuggest — suggested reply to a Bike Anjo support ticket, in shadow. RAG on the bot index.

Contract: contracts/bikeanjo/reply-suggest.schema.json · prompt reply-v1 · hints rag/retrieval-hints.json.
Nothing here is ever sent: the team reads the suggestion next to the reply box. no_answer is a
valid success. Grave tickets (harassment, violence, threat) never reach the model.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.bikeanjo.common import (
    PortError,
    chat_json,
    clamp_confidence,
    compact_json,
    fold,
    grave_hits,
    load_prompt,
    load_retrieval_hints,
)
from app.config import settings
from app.rag.retrieve import retrieve
from app.registry import get_rag_policies

PROMPT_VERSION = "reply-v1"
PORT = "replySuggest"

BOOST = 0.05
DOWNRANK = 0.08

ALLOWED_URL_HOSTS = frozenset({"bikeanjo.org", "www.bikeanjo.org", "cadastro.bikeanjo.org", "sistema.bikeanjo.org"})
ALLOWED_EMAILS = frozenset({"contato@bikeanjo.org"})

_URL_RE = re.compile(r"(?:https?://|www\.)[^\s)>\]]+|\bbit\.ly/\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}")
# Promises in the team's name — the model executes nothing. Matched on fold().
_PROMISE_RE = re.compile(
    r"\bja (exclui|excluimos|apaguei|apagamos|resolvi|resolvemos|atualizei|atualizamos|enviei|enviamos|"
    r"cancelei|cancelamos|alterei|alteramos|corrigi|corrigimos)|"
    r"\b(vou|vamos) (te |lhe )?(ligar|enviar|mandar|excluir|apagar|resolver|retornar em)|"
    r"\bte (enviei|mandei|liguei)\b|com sucesso|magic="
)


class TicketContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    has_account: bool = False
    page_url: str | None = None
    city: str | None = None
    state: str | None = None


class ReplySuggestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source: Literal["support_ticket"] = "support_ticket"
    ticket_id: str
    channel: Literal["platform", "visitor", "site"]
    subject: str = Field(min_length=1, max_length=500)
    message: str = Field(min_length=1, max_length=8000)
    context: TicketContext = TicketContext()

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _id_as_str(cls, v: object) -> object:
        return str(v) if isinstance(v, int) else v


def doc_name(path: str) -> str:
    return PurePosixPath(path or "").stem


def apply_port_hints(chunks: list[dict], port: str = PORT) -> list[dict]:
    """Boost / downrank by path substring (lower distance = better), then re-sort."""
    hints = (load_retrieval_hints().get("ports") or {}).get(port) or {}
    boost = hints.get("boost_path_substrings") or []
    down = hints.get("downrank_path_substrings") or []
    exclude = hints.get("exclude_path_substrings") or []
    out = []
    for c in chunks:
        path = c.get("path") or ""
        if any(s in path for s in exclude):
            continue
        d = c.get("distance")
        adj = float(d) if d is not None else 2.0
        if any(s in path for s in boost):
            adj -= BOOST
        if any(s in path for s in down):
            adj += DOWNRANK
        out.append({**c, "adjusted_distance": adj})
    out.sort(key=lambda c: c["adjusted_distance"])
    return out


async def retrieve_context(project_id: str, project: dict, req: ReplySuggestRequest) -> list[dict]:
    hints = (load_retrieval_hints().get("ports") or {}).get(PORT) or {}
    top_k = int(hints.get("top_k_suggest") or 6)
    policies = get_rag_policies(project)
    max_dist = float(policies.get("max_chunk_distance", 1.0))
    cfg = project.get("config_json") if isinstance(project.get("config_json"), dict) else {}
    embed_model = (cfg or {}).get("embedding_model") or "mxbai-embed-large"
    query = f"{req.subject}\n{req.message}"
    try:
        chunks = await retrieve(project_id, query, top_k=max(top_k * 2, 10), embedding_model=embed_model)
    except Exception as e:
        raise PortError("model_error", f"Falha na busca da base: {e!s}"[:300])
    kept = [c for c in chunks if c.get("distance") is None or float(c["distance"]) <= max_dist]
    return apply_port_hints(kept)[:top_k]


def context_block(chunks: list[dict]) -> str:
    parts: list[str] = []
    total = 0
    for c in chunks:
        block = f"[{doc_name(c.get('path', ''))}]\n{(c.get('snippet') or '').strip()}"
        if total + len(block) > settings.bikeanjo_reply_rag_context_max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts)


def system_prompt() -> str:
    return (
        load_prompt("reply-suggest-v1.md")
        + "\n\nResponda com UM objeto JSON com as chaves suggested_reply, no_answer, confidence, "
        "sources — nada fora dele."
    )


def user_prompt(req: ReplySuggestRequest, block: str) -> str:
    ticket = {
        "channel": req.channel,
        "subject": req.subject,
        "message": req.message,
        "context": req.context.model_dump(),
    }
    return f"Chamado:\n{compact_json(ticket)}\n\nTrechos da base (use só isto como fato):\n{block}"


def validate_model_output(obj: dict[str, Any]) -> list[str]:
    if not isinstance(obj.get("no_answer"), bool):
        return ["no_answer precisa ser true ou false"]
    return []


def reply_violations(reply: str) -> list[str]:
    """Why a suggestion cannot be shown as a draft: promise, foreign link, contact, magic link."""
    found: list[str] = []
    if _PROMISE_RE.search(fold(reply)):
        found.append("promise")
    for url in _URL_RE.findall(reply):
        host = re.sub(r"^(https?://)", "", url.lower()).split("/")[0].rstrip(".,;:!?")
        if host not in ALLOWED_URL_HOSTS:
            found.append("url_not_allowed")
            break
    if any(e.lower().rstrip(".,;:") not in ALLOWED_EMAILS for e in _EMAIL_RE.findall(reply)):
        found.append("email_not_allowed")
    if _PHONE_RE.search(reply):
        found.append("phone")
    return found


def _no_answer(model: str, warnings: list[str], confidence: float = 0.0) -> dict[str, Any]:
    return {
        "status": "ok",
        "suggested_reply": "",
        "no_answer": True,
        "confidence": confidence,
        "sources": [],
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "warnings": sorted(set(warnings)),
    }


def postprocess(obj: dict[str, Any], chunks: list[dict], model: str) -> dict[str, Any]:
    warnings: list[str] = []
    reply = str(obj.get("suggested_reply") or "").strip()
    confidence = clamp_confidence(obj.get("confidence"))
    if obj.get("no_answer") is True or not reply:
        return _no_answer(model, warnings, confidence)

    violations = reply_violations(reply)
    if violations:
        return _no_answer(model, [f"blocked:{v}" for v in violations])

    retrieved = list(dict.fromkeys(doc_name(c.get("path", "")) for c in chunks))
    sources: list[str] = []
    for s in obj.get("sources") or []:
        name = doc_name(str(s))
        match = next((r for r in retrieved if name and (name == r or name in r or r in name)), None)
        if match and match not in sources:
            sources.append(match)
    if not sources:
        sources = retrieved
        warnings.append("sources_inferred")
    if len(reply) > 800:
        warnings.append("long_reply")

    return {
        "status": "ok",
        "suggested_reply": reply,
        "no_answer": False,
        "confidence": confidence,
        "sources": sources,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "warnings": sorted(set(warnings)),
    }


async def run(req: ReplySuggestRequest, project_id: str, project: dict | None) -> dict[str, Any]:
    if grave_hits(req.subject, req.message):
        return _no_answer("guard", ["grave_routed_to_human"], confidence=1.0)
    if not project:
        raise PortError("model_error", f"Projeto {project_id} sem configuração no serviço.")
    chunks = await retrieve_context(project_id, project, req)
    if not chunks:
        return _no_answer("guard", ["no_context"])
    obj, model = await chat_json(
        project,
        system=system_prompt(),
        user=user_prompt(req, context_block(chunks)),
        validate=validate_model_output,
    )
    return postprocess(obj, chunks, model)


def audit_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {k: result.get(k) for k in ("no_answer", "sources", "confidence", "warnings", "prompt_version")}
