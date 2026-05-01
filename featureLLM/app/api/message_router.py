"""POST /router — message router: suggests ask vs flow using project index + LLM."""
import asyncio
import json
import re

import ollama
from fastapi import APIRouter, Depends

from app.auth import require_token
from app.config import settings
from app.registry import get_project, get_rag_policies
from app.rag.retrieve import retrieve
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["router"])

MAX_CHUNK_DISTANCE = 1.2

# Canonical routes for WhatsApp clients (zapzap LLM_API_CONTRACT.md)
ZAPZAP_ROUTES = frozenset(
    {
        "ask",
        "cadastro",
        "saudacao",
        "escalar_humano",
        "documento",
        "status",
        "agradecimento",
    }
)

ROUTER_SYSTEM = """You are a triage router for a message API. Your goal is to decide if you can answer immediately or if we should escalate to a specialist.

Available specialist targets:
- compact: for JSON extraction, classification, or short structured tasks.
- smart: for deep RAG, long answers, or complex context.
- reasoner: for logical chains, debugging, math, or "why" questions.

Task types: chitchat, extract, rag_deep, reasoning, classification.

You must reply with a single valid JSON object (no markdown fences, no prose outside JSON) with these keys:
{
  "action": "answer_now" | "escalate",
  "suggested_route": "ask" | "cadastro" | "saudacao" | "escalar_humano" | "documento" | "status" | "agradecimento",
  "answer": "Portuguese reply text or null",
  "escalate_to": "compact" | "smart" | "reasoner" | "auto" | null,
  "obs": "short note for the specialist or null",
  "task_type": "chitchat" | "extract" | "rag_deep" | "reasoning" | "classification" | null,
  "confidence": 0.0
}

Rules:
- If action is "answer_now", "answer" must be a non-empty friendly Portuguese string; set escalate_to null.
- If action is "escalate", set answer null and set escalate_to (use "auto" if unsure).
- "confidence" must be a number between 0 and 1 (not the words high/medium/low).

Heuristics for suggested_route (ZAPZAP):
- ask: general questions.
- cadastro: registration/signup.
- saudacao: greetings.
- escalar_humano: human attendant request.
- documento: files/docs.
- status: progress check.
- agradecimento: thanks.

Always include "suggested_route" in the JSON object."""


class RouterRequest(BaseModel):
    message: str = Field(..., description="User message text")
    project_id: str | None = Field(None, description="Project slug; when set, uses flow map and library")
    user_name: str | None = Field(None, description="User display name for context")
    user_registered: bool | None = Field(None, description="Phone already in the system")
    onboarding_active: bool | None = Field(None, description="User is mid onboarding flow")
    onboarding_completed: bool | None = Field(None, description="User finished onboarding")
    current_flow: str | None = Field(None, description="Current flow id if user is in a flow")
    current_step: str | None = Field(None, description="Current step/level within flow")
    last_messages: list[str] | None = Field(None, description="Last N messages (user/assistant) for context")
    model: str | None = Field(
        None,
        description="Model alias: fast | compact | smart | reasoner, or explicit Ollama tag",
    )


class RouterResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str = Field(..., description="answer_now | escalate")
    suggested_route: str = Field(
        ...,
        description="Canonical intent: ask, cadastro, saudacao, escalar_humano, documento, status, agradecimento",
    )
    answer: str | None = Field(None, description="Response if action=answer_now")
    escalate_to: str | None = Field(None, description="compact | smart | reasoner | auto")
    obs: str | None = Field(None, description="Note for specialist")
    task_type: str | None = Field(None, description="chitchat | extract | rag_deep | reasoning | classification")
    confidence: float = Field(0.0, description="0.0 to 1.0")


def _parse_router_llm_response(raw: str) -> dict:
    """Extract structured triage data from LLM output (expects JSON)."""
    try:
        # Try to find JSON block if model was verbose
        if "{" in raw and "}" in raw:
            json_str = raw[raw.find("{") : raw.rfind("}") + 1]
            data = json.loads(json_str)
        else:
            data = json.loads(raw)
    except Exception:
        # Fallback for old/failed models
        return {
            "action": "escalate",
            "suggested_route": "ask",
            "escalate_to": "auto",
            "task_type": "rag_deep",
            "confidence": 0.5,
            "obs": f"Falha ao parsear JSON: {raw[:100]}",
        }

    # Normalize fields
    data.setdefault("action", "escalate")
    data.setdefault("suggested_route", "ask")
    data.setdefault("confidence", 0.5)
    return data


def _normalize_suggested_route(route: str) -> str:
    """Map flow slugs from the index to zapzap canonical routes."""
    r = (route or "").strip().lower()
    if not r:
        return "ask"
    if r in ZAPZAP_ROUTES:
        return r
    if "cadastro" in r or "registro" in r or "signup" in r or "cadastr" in r:
        return "cadastro"
    if re.match(r"^[a-z0-9_]+$", r):
        return "ask"
    return "ask"


def _coerce_confidence(raw: object) -> float:
    """Map LLM confidence to 0..1 (accepts legacy high/medium/low strings)."""
    if isinstance(raw, bool):
        return 0.9 if raw else 0.4
    if isinstance(raw, (int, float)):
        return max(0.0, min(1.0, float(raw)))
    if raw is None:
        return 0.5
    s = str(raw).strip().lower()
    if s in ("high", "alta"):
        return 0.85
    if s in ("medium", "med", "média", "media", "médio", "medio"):
        return 0.55
    if s in ("low", "baixa", "baixo"):
        return 0.35
    try:
        return max(0.0, min(1.0, float(s.replace(",", "."))))
    except ValueError:
        return 0.5


def _normalize_router_action(raw: object) -> str:
    a = (str(raw).strip().lower() if raw is not None else "") or "escalate"
    if a in ("answer_now", "answer-now", "answernow", "immediate", "now"):
        return "answer_now"
    return "escalate"


_VALID_ESCALATE = frozenset({"compact", "smart", "reasoner", "auto"})


def _normalize_escalate_token(raw: object) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    return s if s in _VALID_ESCALATE else None


def _finalize_router_response(data: dict) -> RouterResponse:
    """Normalize LLM output into RouterResponse (stable types, no extra-key crashes)."""
    action = _normalize_router_action(data.get("action"))
    suggested_route = _normalize_suggested_route(str(data.get("suggested_route", "ask")))
    confidence = _coerce_confidence(data.get("confidence"))

    answer = data.get("answer")
    if answer is not None and not isinstance(answer, str):
        answer = str(answer)
    if answer is not None:
        answer = answer.strip() or None

    obs = data.get("obs")
    if obs is not None and not isinstance(obs, str):
        obs = str(obs)
    if obs and len(obs) > 2000:
        obs = obs[:1997] + "..."

    task_type = data.get("task_type")
    if task_type is not None and not isinstance(task_type, str):
        task_type = str(task_type)

    escalate_to = _normalize_escalate_token(data.get("escalate_to"))

    if action == "answer_now" and not answer:
        action = "escalate"
        escalate_to = escalate_to or "auto"
        tail = "router: answer_now sem texto, escalado"
        obs = f"{obs}; {tail}" if (obs and str(obs).strip()) else tail

    if action == "escalate":
        answer = None
    else:
        escalate_to = None

    return RouterResponse(
        action=action,
        suggested_route=suggested_route,
        answer=answer,
        escalate_to=escalate_to,
        obs=obs,
        task_type=task_type,
        confidence=confidence,
    )


@router.post("/router", response_model=RouterResponse)
async def route_message(
    body: RouterRequest,
    _: None = Depends(require_token),
) -> RouterResponse:
    """
    Triage-first router: decides whether to answer immediately or escalate to a specialist.
    """
    if not body.project_id:
        return RouterResponse(
            action="escalate",
            suggested_route="ask",
            escalate_to="auto",
            task_type="rag_deep",
            confidence=0.0,
            obs="Sem project_id; sugestão genérica.",
        )

    project = await get_project(body.project_id)
    if not project:
        return RouterResponse(
            action="escalate",
            suggested_route="ask",
            escalate_to="auto",
            task_type="rag_deep",
            confidence=0.0,
            obs="Projeto não encontrado.",
        )

    policies = get_rag_policies(project)
    top_k = policies.get("max_chunks_to_retrieve", 5)
    embed_model = "nomic-embed-text"
    if isinstance(project.get("config_json"), dict):
        embed_model = (project["config_json"] or {}).get("embedding_model") or embed_model

    chunks = await retrieve(body.project_id, body.message, top_k=top_k, embedding_model=embed_model)
    chunks = [c for c in chunks if c.get("distance") is None or c["distance"] <= MAX_CHUNK_DISTANCE]

    context_parts = []
    for c in chunks:
        context_parts.append(f"[{c.get('path', '')}]\n{c.get('snippet', '')}")
    context_text = "\n\n---\n\n".join(context_parts) if context_parts else "(Nenhum trecho relevante no índice.)"

    user_parts = [f"Mensagem do usuário: {body.message}"]
    if body.user_name:
        user_parts.append(f"Nome: {body.user_name}")
    if body.user_registered is not None:
        user_parts.append(f"Usuário já cadastrado no sistema: {body.user_registered}")
    if body.onboarding_active is not None:
        user_parts.append(f"Onboarding em andamento: {body.onboarding_active}")
    if body.onboarding_completed is not None:
        user_parts.append(f"Onboarding já concluído: {body.onboarding_completed}")
    if body.current_flow:
        user_parts.append(f"Fluxo atual: {body.current_flow}")
    if body.current_step:
        user_parts.append(f"Etapa atual: {body.current_step}")
    if body.last_messages:
        user_parts.append("Últimas mensagens:\n" + "\n".join(body.last_messages[:5]))
    user_parts.append("\nContexto do projeto (biblioteca + mapa de fluxos):\n" + context_text)
    user_content = "\n".join(user_parts)

    try:
        response = await asyncio.to_thread(
            ollama.chat,
            model=settings.get_model_name(body.model, default_alias="fast"),
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            options={"temperature": 0.1, "num_predict": 512},
            format="json",
        )
        raw = (response.get("message") or {}).get("content") or ""
    except Exception as e:
        return RouterResponse(
            action="escalate",
            suggested_route="ask",
            escalate_to="auto",
            task_type="rag_deep",
            confidence=0.0,
            obs=f"Erro ao consultar LLM: {e}",
        )

    data = _parse_router_llm_response(raw)
    data["suggested_route"] = _normalize_suggested_route(data.get("suggested_route", "ask"))

    finalized = _finalize_router_response(data)

    # Resolve specialist after finalization so answer_now→escalate (empty answer) gets a concrete model
    if finalized.action == "escalate" and (
        not finalized.escalate_to or finalized.escalate_to == "auto"
    ):
        from app.router.selection import select_specialist_alias

        new_et = select_specialist_alias(
            task_type=data.get("task_type"),
            prompt=body.message,
            has_retrieve_context=bool(chunks),
            context_token_count=len(context_text) // 4,
        )
        finalized = finalized.model_copy(update={"escalate_to": new_et})

    if finalized.action == "escalate" and finalized.escalate_to not in (None, "auto"):
        from app.jobs.worker import speculative_warmup

        asyncio.create_task(speculative_warmup(finalized.escalate_to))

    return finalized
