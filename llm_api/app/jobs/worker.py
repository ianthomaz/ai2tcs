"""Process one job: RAG retrieval + Ollama completion with conversation context."""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app import db as db_module
from app.config import settings
from app.llm import get_provider
from app.registry import (
    get_project,
    get_rag_feature_flags,
    get_rag_mode,
    get_rag_policies,
    get_llm_config,
    get_behavior_instruction_inline,
    get_behavior_instruction_path,
)
from app.rag.prompt import build_messages, is_shareable_url
from app.rag.answer_guard import guard_answer_for_profile
from app.rag.retrieve import retrieve

logger = logging.getLogger(__name__)

# Run maintenance every 5 days, only during "madrugada" (2h–6h Brazil time).
_MAINTENANCE_INTERVAL_SEC = 5 * 86400  # 5 days
_BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")
_MADRUGADA_START = 2   # 02:00
_MADRUGADA_END = 6     # 06:00 (exclusive)
_last_maintenance: datetime | None = None

# Default distance threshold (cosine, range [0, 2]). Now configurable per project
# via policies.max_chunk_distance. Reduced from 1.2 to 1.0 (março 2026) because
# weakly-related chunks (distance 1.0-1.2) pollute context and cause generic responses.
MAX_CHUNK_DISTANCE = 1.0


def _filter_chunks_by_distance(chunks: list[dict], max_distance: float = MAX_CHUNK_DISTANCE) -> list[dict]:
    """Remove chunks that are too far from the query (likely irrelevant noise)."""
    return [c for c in chunks if c.get("distance") is None or c["distance"] <= max_distance]


def _rerank_for_diversity(chunks: list[dict], max_per_doc: int = 2) -> list[dict]:
    """Re-rank chunks to limit redundancy from the same document.

    Problem (março 2026): when a single long document dominates retrieval, the LLM
    gets 5 chunks from the same file — often overlapping content — wasting context
    window and producing repetitive answers.

    Solution: keep at most max_per_doc chunks per source document (path), filling
    remaining slots with chunks from other documents for diversity.
    Chunks are already sorted by distance (best first) from Chroma.
    """
    if not chunks or max_per_doc < 1:
        return chunks
    doc_counts: dict[str, int] = {}
    selected: list[dict] = []
    deferred: list[dict] = []
    for c in chunks:
        path = c.get("path", "")
        count = doc_counts.get(path, 0)
        if count < max_per_doc:
            selected.append(c)
            doc_counts[path] = count + 1
        else:
            deferred.append(c)
    # Fill remaining slots with deferred chunks (if we have capacity)
    # This preserves the original total count
    return selected + deferred


# --- Sanitização pós-processamento ---
# Cada regra corrige um desvio recorrente do modelo 7B/8B que o prompt base não consegue
# eliminar de forma confiável. Regras são conservadoras: padrões específicos, com log.

# Desvio: modelo abre resposta com meta-frases ("Com base no contexto fornecido, ...")
# Adicionado: março 2026. Exemplo: "Com base no contexto fornecido, a Mobi oferece..."
_META_PHRASE_PREFIXES = re.compile(
    r"^(?:"
    r"Com base (?:no contexto fornecido|apenas na informação fornecida|nas informações (?:disponíveis|fornecidas)),?\s*"
    r"|Segundo o (?:conteúdo|contexto),?\s*"
    r"|De acordo com (?:o contexto|as informações (?:disponíveis|fornecidas)),?\s*"
    r"|A pergunta é sobre[^.]*\.\s*"
    r")",
    re.IGNORECASE,
)

# Desvio: modelo gera frase longa negativa quando não tem contexto suficiente.
# Adicionado: março 2026. Exemplo: "Não encontrei informação suficiente na base de conhecimento..."
_NEGATIVE_FILLER = re.compile(
    r"Não encontrei informação suficiente na base de conhecimento para responder essa pergunta\.?\s*",
    re.IGNORECASE,
)


def _sanitize_answer(answer: str) -> str:
    """Apply minimal, targeted post-processing to fix known LLM generation errors.

    Rules are intentionally conservative — only well-identified patterns with
    context guards. Each rule logs when applied for observability.
    """
    original = answer

    # 1. Remove meta-phrase prefixes (modelo 7B/8B ignora proibição do prompt ~20% das vezes)
    answer = _META_PHRASE_PREFIXES.sub("", answer, count=1)

    # 2. Remove frase longa negativa de fallback
    answer = _NEGATIVE_FILLER.sub("", answer)

    # 3. Fix "falecimento" typo only in contact context (regra original, preservada)
    if "falecimento" in answer:
        death_context = any(
            p in answer.lower()
            for p in ("falecimento de ", "falecimento do ", "em caso de falecimento", "falecimento de um")
        )
        wrong_contact_pattern = "contatos para falecimento" in answer or " para falecimento ou " in answer
        if wrong_contact_pattern and not death_context:
            answer = answer.replace(" para falecimento ", " para fale conosco ")
            answer = answer.replace("contatos para falecimento", "contatos para fale conosco")
            answer = answer.replace("informações sobre contatos para falecimento", "informações sobre contato / fale conosco")

    answer = answer.strip()

    if answer != original:
        logger.info("sanitize_answer applied corrections (len %d → %d)", len(original), len(answer))

    return answer


REFLECTION_PROMPT = """\
Pergunta: {question}
Contexto RAG (trechos):
{context}

Resposta gerada:
{answer}

A resposta está embasada no contexto? Responda em JSON: {{"grounded": "SIM"|"PARCIAL"|"NAO", "corrected": "texto corrigido ou null"}}
Se PARCIAL ou NAO, preencha corrected usando apenas o contexto. Se SIM, corrected null.
"""


async def _reflect_on_answer(
    *,
    provider,
    question: str,
    chunks: list[dict],
    answer: str,
    llm_config: dict,
) -> str:
    """Optional self-RAG pass with fast model to reduce hallucinations."""
    context = "\n---\n".join((c.get("snippet") or "")[:800] for c in chunks[:4])
    prompt = REFLECTION_PROMPT.format(question=question[:2000], context=context[:6000], answer=answer[:2000])
    fast_model = settings.get_model_name("fast", default_alias="fast")
    fast_opts = {**llm_config, "temperature": 0.2, "num_predict": 512}
    try:
        raw = await provider.chat(
            model=fast_model,
            messages=[{"role": "user", "content": prompt}],
            options=fast_opts,
        )
        if "{" in raw and "}" in raw:
            blob = raw[raw.find("{") : raw.rfind("}") + 1]
            data = json.loads(blob)
            corrected = data.get("corrected")
            if isinstance(corrected, str) and corrected.strip():
                return corrected.strip()
    except Exception as exc:
        logger.warning("RAG reflection skipped: %s", exc)
    return answer


def _profile_from_request_context(user_context: dict) -> dict:
    """Build prompt profile dict from request-time user_context (zapzap / sistemaBA).

    clearance / intended_clearance are intentionally absent: they are an authorization
    tier (NOIA), validated before this call, and the flows where I/A can execute
    anything do not consult the LLM semantically. Surfacing a permission level in the
    prompt only invites the model to reason about access, which it has no authority
    over. They remain on the stored job payload — just not in the prompt.
    """
    profile: dict = {}
    if user_context.get("name"):
        profile["display_name"] = user_context["name"]
    if user_context.get("birth_date"):
        profile["birth_date"] = user_context["birth_date"]
    meta = {}
    for key in (
        "cep",
        "city",
        "state",
        "health",
        "interesse",
        "registered",
        "journey_kind",
        "journey_destination",
        "next_event_name",
        "next_event_at",
        "current_time",
    ):
        if user_context.get(key) is not None and user_context.get(key) != "":
            meta[key] = user_context[key]
    # The journey destination is normally an internal reference (event id, system
    # pointer) that the platform resolves later, not a link. The model cannot resolve
    # it and would only leak the raw id, so it passes through only when it already is
    # a usable URL.
    if "journey_destination" in meta and not is_shareable_url(meta["journey_destination"]):
        del meta["journey_destination"]
    if meta:
        profile["metadata"] = meta
    return profile


def _parse_job_user_context(
    raw: dict | str | None,
) -> tuple[dict, list[dict] | None, str | None, str | None, str | None]:
    """Split stored user_context_json into profile, history, system prompt, model alias, callback URL."""
    if raw is None:
        return {}, None, None, None, None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}, None, None, None, None
    if not isinstance(raw, dict):
        return {}, None, None, None, None
    data = dict(raw)
    hist = data.pop("__llm_history", None)
    sys_pfx = data.pop("__llm_system_prompt", None)
    model_alias = data.pop("__llm_model", None)
    callback_url = data.pop("__llm_callback_url", None)
    client_hist: list[dict] | None = None
    if isinstance(hist, list) and hist:
        client_hist = []
        for row in hist:
            if not isinstance(row, dict):
                continue
            role = row.get("role") or "user"
            content = row.get("content") or row.get("text") or ""
            client_hist.append({"role": role, "content": str(content)[:2000]})
    sys_str = str(sys_pfx).strip() if sys_pfx else None
    model_str = str(model_alias).strip() if model_alias else None
    cb = str(callback_url).strip() if callback_url else None
    return data, client_hist, sys_str, model_str, cb


async def _fire_job_callback(
    callback_url: str,
    *,
    job_id: str,
    status: str,
    answer: str | None,
    sources: list[dict],
) -> None:
    import httpx

    if not callback_url.startswith("https://"):
        logger.warning("Skipping callback for job %s: URL must be https://", job_id)
        return
    payload = {
        "job_id": job_id,
        "status": status,
        "answer": answer,
        "sources": sources,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(callback_url, json=payload)
    except Exception as exc:
        logger.warning("Callback failed for job %s: %s", job_id, exc)


async def run_rag_job(
    job_id: str,
    project_id: str,
    question: str,
    user_id: str | None = None,
    user_context: dict | str | None = None,
) -> None:
    """Run RAG + LLM for a text question and persist result to the Job row."""
    try:
        await db_module.job_update_status(job_id, "working", progress="loading_project")
        profile_ctx, client_conversation_override, client_system_prefix, model_alias, callback_url = (
            _parse_job_user_context(user_context)
        )

        project = await get_project(project_id)
        if not project:
            await db_module.job_update_status(job_id, "failed", error_message="project not found")
            return
        policies = get_rag_policies(project)
        rag_mode = get_rag_mode(project)
        top_k = policies.get("max_chunks_to_retrieve", 5)
        embed_model = "mxbai-embed-large"
        if isinstance(project.get("config_json"), dict):
            embed_model = (project["config_json"] or {}).get("embedding_model") or embed_model

        # RAG retrieval (skipped when rag_mode == "disabled")
        chunks: list[dict] = []
        if rag_mode != "disabled":
            await db_module.job_update_status(job_id, "working", progress="retrieving_context")
            chunks = await retrieve(project_id, question, top_k=top_k, embedding_model=embed_model)
            max_dist = policies.get("max_chunk_distance", MAX_CHUNK_DISTANCE)
            chunks = _filter_chunks_by_distance(chunks, max_distance=max_dist)

            # Deep Search Logic: if configured or if we found too little, search again with wider criteria
            depth = policies.get("search_depth", "standard")
            if (depth == "deep" or not chunks) and top_k < 15:
                logger.info("Deep search triggered for job %s (depth=%s, chunks_found=%d)", job_id, depth, len(chunks))
                deep_top_k = 12
                deep_max_dist = max_dist * 1.3  # 30% more permissive
                more_chunks = await retrieve(project_id, question, top_k=deep_top_k, embedding_model=embed_model)
                more_chunks = _filter_chunks_by_distance(more_chunks, max_distance=deep_max_dist)

                existing_ids = {c.get("id") for c in chunks if c.get("id")}
                for c in more_chunks:
                    if c.get("id") not in existing_ids:
                        chunks.append(c)
                chunks.sort(key=lambda x: x.get("distance", 2.0))
                chunks = chunks[:10]

            chunks = _rerank_for_diversity(chunks)

        # Load user context (if identified)
        conversation_history: list[dict] = []
        user_profile: dict | None = None
        conversation_summaries: list[dict] = []
        if user_id:
            if client_conversation_override is None:
                conversation_history = await db_module.conversation_get_recent(user_id, project_id, limit=10)
            user_profile = await db_module.user_profile_get(user_id, project_id)
            conversation_summaries = await db_module.summary_get_recent(user_id, project_id, limit=3)
            # Persist the user's question in conversation history
            await db_module.conversation_append(user_id, project_id, "user", question, job_id=job_id)

        # Request-time user_context (e.g. from zapzap) overrides/supplements DB profile for this reply
        if profile_ctx:
            request_profile = _profile_from_request_context(profile_ctx)
            if request_profile:
                base = dict(user_profile) if user_profile else {}
                base.update(request_profile)
                if request_profile.get("metadata") and base.get("metadata"):
                    base["metadata"] = {**(base.get("metadata") or {}), **request_profile["metadata"]}
                user_profile = base

        # Project-specific behavior instruction (inline in config or file in project folder)
        extra_instruction: str | None = get_behavior_instruction_inline(project)
        if not extra_instruction:
            rel_path = get_behavior_instruction_path(project)
            if rel_path and project.get("sources"):
                first_source = project["sources"][0]
                root = Path(first_source) if Path(first_source).is_dir() else Path(first_source).parent
                full_path = root / rel_path
                if full_path.is_file():
                    try:
                        extra_instruction = full_path.read_text(encoding="utf-8", errors="replace").strip()
                    except OSError:
                        logger.warning("Could not read behavior instruction file: %s", full_path)

        # Load LLM config from project (or defaults)
        llm_config = get_llm_config(project)

        system_msg, user_msg = build_messages(
            project,
            question,
            chunks,
            conversation_history=conversation_history,
            user_profile=user_profile,
            conversation_summaries=conversation_summaries,
            extra_system_instruction=extra_instruction,
            conversation_override=client_conversation_override,
            client_system_prompt_prefix=client_system_prefix,
            llm_config=llm_config,
        )
        await db_module.job_update_status(job_id, "working", progress="generating")

        model_name = settings.get_model_name(model_alias, default_alias="smart")
        provider = get_provider(project)
        answer = await provider.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            options=llm_config,
        )

        # Post-processing: fix known LLM generation errors (meta-phrases, typos, filler)
        answer = _sanitize_answer(answer)
        answer = guard_answer_for_profile(answer, project)

        if get_rag_feature_flags(project)["rag_reflection_enabled"] and chunks and answer:
            answer = await _reflect_on_answer(
                provider=provider,
                question=question,
                chunks=chunks,
                answer=answer,
                llm_config=llm_config,
            )

        # Persist assistant response in conversation history
        if user_id and answer:
            await db_module.conversation_append(user_id, project_id, "assistant", answer, job_id=job_id)

        sources = [
            {
                "id": c.get("id", ""),
                "path": c.get("path", ""),
                "snippet": (c.get("snippet") or "")[:500],
                "url": c.get("url") or None,
            }
            for c in chunks
        ]
        confidence = "high" if chunks else "low"
        if not chunks and rag_mode == "required":
            status = policies.get("when_no_answer", "no_answer")
        else:
            status = "done"
        await db_module.job_update_status(
            job_id,
            status,
            progress="complete",
            answer=answer,
            sources=sources,
            confidence=confidence,
        )
        if callback_url:
            await _fire_job_callback(
                callback_url,
                job_id=job_id,
                status=status,
                answer=answer,
                sources=sources,
            )
        logger.info("job %s completed with status %s (user=%s)", job_id, status, user_id or "anonymous")
    except Exception as e:
        logger.exception("job %s failed", job_id)
        await db_module.job_update_status(job_id, "failed", error_message=str(e))


async def process_job(
    job_id: str,
    project_id: str,
    question: str,
    user_id: str | None = None,
    user_context: dict | str | None = None,
) -> None:
    """Text ask job: same as run_rag_job (kept for callers)."""
    await run_rag_job(job_id, project_id, question, user_id=user_id, user_context=user_context)


async def process_audio_job(job: dict) -> None:
    """Transcribe uploaded audio; audio_transcribe ends here, audio_ask continues with run_rag_job."""
    import time
    from pathlib import Path

    from app.config import settings
    from app.stt import metrics as stt_metrics
    from app.stt.whisper_client import transcribe_audio_file

    job_id = job["id"]
    raw_path = job.get("audio_path")
    path = Path(raw_path) if raw_path else None
    if not path or not path.is_file():
        await db_module.job_update_status(job_id, "failed", error_message="audio file missing or already removed")
        return

    kind = (job.get("job_kind") or "ask").strip()
    user_ctx = job.get("user_context") if isinstance(job.get("user_context"), dict) else {}
    lang_override = None
    if user_ctx.get("__stt_language"):
        lang_override = str(user_ctx["__stt_language"]).strip() or None

    await db_module.job_update_status(job_id, "working", progress="transcribing")
    t0 = time.perf_counter()
    try:
        result = await asyncio.to_thread(transcribe_audio_file, path, lang_override)
    except Exception as e:
        stt_metrics.record_stt_failure()
        logger.exception("stt failed job %s", job_id)
        await db_module.job_update_status(job_id, "failed", error_message=f"stt: {e}")
        return
    finally:
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            logger.warning("could not remove temp audio %s", path)

    transcribe_seconds = time.perf_counter() - t0
    stt_metrics.record_stt_success(transcribe_seconds)

    stt_metadata = {
        "language": result.language,
        "duration_seconds": result.duration_seconds,
        "segment_count": result.segment_count,
        "model": settings.whisper_model_size,
        "transcribe_seconds": round(transcribe_seconds, 3),
    }
    text = (result.text or "").strip()
    q_for_row = text[:2000] if text else "[audio]"

    if not text:
        stt_metrics.record_stt_failure()
        await db_module.job_update_after_stt(
            job_id,
            transcript="",
            stt_metadata=stt_metadata,
            question=q_for_row,
            clear_audio_path=True,
        )
        await db_module.job_update_status(job_id, "failed", error_message="stt: empty transcript")
        return

    await db_module.job_update_after_stt(
        job_id,
        transcript=text,
        stt_metadata=stt_metadata,
        question=q_for_row,
        clear_audio_path=True,
    )

    if kind == "audio_transcribe":
        await db_module.job_update_status(
            job_id,
            "done",
            progress="complete",
            answer=text,
            confidence="high",
        )
        logger.info("job %s audio_transcribe done", job_id)
        return

    if kind == "audio_ask":
        # Strip internal STT-only keys before RAG
        ctx = dict(user_ctx)
        ctx.pop("__stt_language", None)
        await run_rag_job(
            job_id,
            job["project_id"],
            text,
            user_id=job.get("user_id"),
            user_context=ctx if ctx else None,
        )
        return

    await db_module.job_update_status(job_id, "failed", error_message=f"unknown audio job_kind: {kind}")


def _is_madrugada_brazil() -> bool:
    """True if current time in Brazil is in madrugada (2h–6h)."""
    now_br = datetime.now(_BRAZIL_TZ)
    return _MADRUGADA_START <= now_br.hour < _MADRUGADA_END


async def _maybe_run_maintenance() -> None:
    """Run conversation maintenance every 5 days, only during madrugada (Brazil)."""
    global _last_maintenance
    now = datetime.now(timezone.utc)
    if not _is_madrugada_brazil():
        return
    if _last_maintenance and (now - _last_maintenance).total_seconds() < _MAINTENANCE_INTERVAL_SEC:
        return
    _last_maintenance = now
    try:
        from app.jobs.conversation_maintenance import summarize_and_purge_old_conversations
        stats = await summarize_and_purge_old_conversations(max_age_days=30)
        if stats["messages_deleted"] > 0 or stats["summaries_created"] > 0:
            logger.info("conversation maintenance (madrugada): %s", stats)
    except Exception as e:
        logger.exception("conversation maintenance failed: %s", e)


async def speculative_warmup(model_alias: str) -> None:
    """Trigger a speculative warm-up for a model alias (Ollama only)."""
    import ollama as _ollama
    try:
        model_name = settings.get_model_name(model_alias)
        logger.info("Speculative warm-up for %s (%s)", model_alias, model_name)
        await asyncio.to_thread(
            _ollama.generate,
            model=model_name,
            prompt="",
            keep_alive="5m",
        )
    except Exception as e:
        logger.warning("Warm-up failed for %s: %s", model_alias, e)


async def _worker_coro(alias_filter: str | None = None) -> None:
    """Background loop: poll Postgres for queued jobs and process.

    If alias_filter is set, only consumes jobs that resolve to that alias.
    """
    worker_label = alias_filter or "generic"
    logger.info("Worker started: %s", worker_label)

    while True:
        try:
            job = await db_module.job_get_next_queued(alias_filter=alias_filter)
            if job:
                kind = (job.get("job_kind") or "ask").strip()
                if kind in ("audio_transcribe", "audio_ask"):
                    await process_audio_job(job)
                else:
                    await process_job(
                        job["id"],
                        job["project_id"],
                        job["question"],
                        user_id=job.get("user_id"),
                        user_context=job.get("user_context"),
                    )
            else:
                # No jobs queued — good time to check maintenance
                if not alias_filter or alias_filter == "fast":
                    await _maybe_run_maintenance()
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("worker error: %s", e)
            await asyncio.sleep(5)
