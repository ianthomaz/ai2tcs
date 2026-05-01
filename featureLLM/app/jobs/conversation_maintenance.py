"""Conversation summarization and cleanup.

Runs every 5 days during madrugada (Brazil), or manually via API.
Processes at most MAX_USERS_PER_RUN user+project pairs per run to avoid overload;
remaining conversations are handled in the next run.
For each user+project with old messages (> 30 days):
  1. Groups messages by month
  2. Calls Ollama to generate a compact summary of each month
  3. Stores summary in conversation_summary table
  4. Deletes the raw messages
"""
import asyncio
import logging
from datetime import datetime, timedelta

import ollama

from app import db as db_module
from app.config import settings

logger = logging.getLogger(__name__)

# Limit users per run so we don't overload; the rest are done in the next run (5 days later).
MAX_USERS_PER_RUN = 10
# Pause between users to avoid hammering Ollama.
SLEEP_BETWEEN_USERS_SEC = 3

SUMMARY_PROMPT = """\
Resuma a conversa abaixo de forma compacta (máximo 300 palavras).
Destaque: tópicos principais discutidos, informações pessoais mencionadas pelo usuário, \
preferências expressas, e qualquer pedido ou problema recorrente.
Mantenha o resumo na mesma língua das mensagens.

Conversa:

{conversation}

Resumo compacto:\
"""


def _format_messages_for_summary(messages: list[dict]) -> str:
    """Format messages into a readable block for the summarizer."""
    lines = []
    for m in messages:
        role = "Usuário" if m["role"] == "user" else "Assistente"
        content = m["content"][:800]
        lines.append(f"[{role}]: {content}")
    return "\n".join(lines)


async def summarize_and_purge_old_conversations(max_age_days: int = 30) -> dict:
    """Summarize and delete conversations older than max_age_days.

    Processes at most MAX_USERS_PER_RUN pairs per run; the rest are left for the next run.
    Returns {"users_processed": N, "summaries_created": N, "messages_deleted": N, "users_remaining": N}.
    """
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    stats = {"users_processed": 0, "summaries_created": 0, "messages_deleted": 0, "users_remaining": 0}

    # Find all distinct user+project pairs with old messages
    async with (await db_module.get_pool()).acquire() as conn:
        pairs = await conn.fetch(
            """
            SELECT DISTINCT user_id, project_id FROM conversation_history
            WHERE created_at < $1
            """,
            cutoff,
        )

    total = len(pairs)
    to_process = pairs[:MAX_USERS_PER_RUN]
    stats["users_remaining"] = max(0, total - len(to_process))

    for i, pair in enumerate(to_process):
        if i > 0:
            await asyncio.sleep(SLEEP_BETWEEN_USERS_SEC)
        user_id = pair["user_id"]
        project_id = pair["project_id"]
        stats["users_processed"] += 1

        old_messages = await db_module.conversation_get_old_messages(user_id, project_id, before=cutoff)
        if not old_messages:
            continue

        # Group by month
        months: dict[str, list[dict]] = {}
        for msg in old_messages:
            period = msg["created_at"].strftime("%Y-%m")
            months.setdefault(period, []).append(msg)

        for period, msgs in months.items():
            conversation_text = _format_messages_for_summary(msgs)
            prompt = SUMMARY_PROMPT.format(conversation=conversation_text)

            try:
                response = await asyncio.to_thread(
                    ollama.chat,
                    model=settings.get_model_name(None, default_alias="fast"),
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1, "num_predict": 512},
                )
                summary = (response.get("message") or {}).get("content") or ""
            except Exception as e:
                logger.error("Failed to summarize %s/%s/%s: %s", user_id, project_id, period, e)
                continue

            if summary:
                await db_module.summary_upsert(user_id, project_id, period, summary, len(msgs))
                ids_to_delete = [m["id"] for m in msgs]
                deleted = await db_module.conversation_delete_by_ids(ids_to_delete)
                stats["summaries_created"] += 1
                stats["messages_deleted"] += deleted
                logger.info(
                    "Summarized %d messages for %s/%s/%s",
                    len(msgs), user_id, project_id, period,
                )

    if stats["users_remaining"] > 0:
        logger.info(
            "conversation maintenance: %d user(s) left for next run (in 5 days)",
            stats["users_remaining"],
        )
    return stats
