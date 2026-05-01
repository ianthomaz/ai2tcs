"""PostgreSQL connection pool and helpers. Schema via Prisma; app uses asyncpg."""
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None
logger = logging.getLogger(__name__)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=1,
            max_size=5,
            command_timeout=60,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def pool():
    p = await get_pool()
    try:
        yield p
    finally:
        pass


def _serialize_sources(sources: list[dict] | None) -> str | None:
    if not sources:
        return None
    return json.dumps(sources)


def _parse_sources(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


# --- Project ---


async def project_get(project_id: str) -> dict | None:
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, project_id, name, sources, config_json, created_at, updated_at
            FROM "Project"
            WHERE project_id = $1
            """,
            project_id,
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "sources": list(row["sources"]) if row["sources"] else [],
            "config_json": row["config_json"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


async def project_get_themes(project_id: str) -> list[str]:
    async with (await get_pool()).acquire() as conn:
        rows = await conn.fetch(
            'SELECT theme FROM project_themes WHERE project_id = $1',
            project_id,
        )
        return [r["theme"] for r in rows]


async def project_list_ids() -> list[str]:
    async with (await get_pool()).acquire() as conn:
        rows = await conn.fetch('SELECT project_id FROM "Project"')
        return [r["project_id"] for r in rows]


# --- Job ---


async def job_create(
    project_id: str,
    question: str,
    question_hash: str | None,
    user_id: str | None = None,
    user_context: dict | None = None,
    job_kind: str = "ask",
    model_alias: str = "smart",
    audio_path: str | None = None,
    job_id: str | None = None,
) -> str:
    jid = job_id if job_id else str(uuid4())
    user_context_raw = json.dumps(user_context) if user_context else None
    async with (await get_pool()).acquire() as conn:
        await conn.execute(
            """
            INSERT INTO "Job" (
                id, project_id, user_id, question, question_hash, user_context_json,
                job_kind, model_alias, audio_path, status, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, 'queued', NOW(), NOW())
            """,
            jid,
            project_id,
            user_id,
            question,
            question_hash,
            user_context_raw,
            job_kind,
            model_alias,
            audio_path,
        )
    return jid


_MAX_AUDIT_ANSWER_CHARS = 100_000


async def job_insert_terminal_audit(
    project_id: str,
    *,
    job_kind: str,
    question: str,
    status: str,
    model_alias: str,
    answer: str | None = None,
    error_message: str | None = None,
    user_context: dict | None = None,
    progress: str | None = None,
) -> str | None:
    """
    Insert a Job row already in a terminal status (never queued).
    Used for sync HTTP paths (e.g. nabil qualify-caption) so the dashboard / stats see activity.
    """
    try:
        jid = str(uuid4())
        user_context_raw = json.dumps(user_context) if user_context else None
        prog = progress if progress is not None else ("complete" if status == "done" else None)
        ans = answer[:_MAX_AUDIT_ANSWER_CHARS] if answer else None
        q = (question or "")[:12000]
        alias = (model_alias or "smart")[:128]
        async with (await get_pool()).acquire() as conn:
            await conn.execute(
                """
                INSERT INTO "Job" (
                    id, project_id, user_id, question, question_hash, user_context_json,
                    job_kind, model_alias, audio_path, status, progress, answer, error_message,
                    created_at, updated_at
                )
                VALUES (
                    $1, $2, NULL, $3, NULL, $4::jsonb,
                    $5, $6, NULL, $7, $8, $9, $10,
                    NOW(), NOW()
                )
                """,
                jid,
                project_id,
                q,
                user_context_raw,
                job_kind,
                alias,
                status,
                prog,
                ans,
                error_message,
            )
        return jid
    except Exception:
        logger.exception("job_insert_terminal_audit failed project_id=%s job_kind=%s", project_id, job_kind)
        return None


async def job_get(job_id: str) -> dict | None:
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, project_id, question, question_hash, status, progress, answer,
                   sources_json, confidence, error_message, created_at, updated_at,
                   job_kind, model_alias, audio_path, transcript, stt_metadata_json
            FROM "Job"
            WHERE id = $1
            """,
            job_id,
        )
        if not row:
            return None
        stt_meta = row["stt_metadata_json"]
        if isinstance(stt_meta, str):
            try:
                stt_meta = json.loads(stt_meta)
            except (json.JSONDecodeError, TypeError):
                stt_meta = None
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "question": row["question"],
            "question_hash": row["question_hash"],
            "status": row["status"],
            "progress": row["progress"],
            "answer": row["answer"],
            "sources": _parse_sources(row["sources_json"]) if isinstance(row["sources_json"], str) else (row["sources_json"] or []),
            "confidence": row["confidence"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "job_kind": row["job_kind"] or "ask",
                "model_alias": row["model_alias"] or "smart",
            "audio_path": row["audio_path"],
            "transcript": row["transcript"],
            "stt_metadata": stt_meta if isinstance(stt_meta, dict) else None,
        }


async def job_update_status(
    job_id: str,
    status: str,
    progress: str | None = None,
    answer: str | None = None,
    sources: list[dict] | None = None,
    confidence: str | None = None,
    error_message: str | None = None,
) -> None:
    updates = ["status = $2", "updated_at = NOW()"]
    args: list = [job_id, status]
    idx = 3
    if progress is not None:
        updates.append(f"progress = ${idx}")
        args.append(progress)
        idx += 1
    if answer is not None:
        updates.append(f"answer = ${idx}")
        args.append(answer)
        idx += 1
    if sources is not None:
        updates.append(f"sources_json = ${idx}")
        args.append(_serialize_sources(sources))
        idx += 1
    if confidence is not None:
        updates.append(f"confidence = ${idx}")
        args.append(confidence)
        idx += 1
    if error_message is not None:
        updates.append(f"error_message = ${idx}")
        args.append(error_message)
    async with (await get_pool()).acquire() as conn:
        await conn.execute(
            f'UPDATE "Job" SET {", ".join(updates)} WHERE id = $1',
            *args,
        )


async def job_update_after_stt(
    job_id: str,
    *,
    transcript: str,
    stt_metadata: dict,
    question: str | None = None,
    clear_audio_path: bool = True,
) -> None:
    """Persist STT output; optionally replace question (e.g. with transcript) and clear temp path."""
    meta_raw = json.dumps(stt_metadata)
    async with (await get_pool()).acquire() as conn:
        if clear_audio_path and question is not None:
            await conn.execute(
                """
                UPDATE "Job" SET transcript = $2, stt_metadata_json = $3::jsonb,
                    question = $4, audio_path = NULL, updated_at = NOW()
                WHERE id = $1
                """,
                job_id,
                transcript,
                meta_raw,
                question,
            )
        elif clear_audio_path:
            await conn.execute(
                """
                UPDATE "Job" SET transcript = $2, stt_metadata_json = $3::jsonb,
                    audio_path = NULL, updated_at = NOW()
                WHERE id = $1
                """,
                job_id,
                transcript,
                meta_raw,
            )
        elif question is not None:
            await conn.execute(
                """
                UPDATE "Job" SET transcript = $2, stt_metadata_json = $3::jsonb,
                    question = $4, updated_at = NOW()
                WHERE id = $1
                """,
                job_id,
                transcript,
                meta_raw,
                question,
            )
        else:
            await conn.execute(
                """
                UPDATE "Job" SET transcript = $2, stt_metadata_json = $3::jsonb,
                    updated_at = NOW()
                WHERE id = $1
                """,
                job_id,
                transcript,
                meta_raw,
            )


async def job_get_next_queued(alias_filter: str | None = None) -> dict | None:
    """Pick next job with status queued (for worker). Uses SELECT FOR UPDATE SKIP LOCKED then UPDATE."""
    where = "status = 'queued'"
    args = []
    if alias_filter:
        where += " AND model_alias = $1"
        args.append(alias_filter)

    async with (await get_pool()).acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""
                SELECT id, project_id, user_id, question, user_context_json, job_kind, model_alias, audio_path
                FROM "Job"
                WHERE {where} ORDER BY created_at ASC LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                *args
            )
            if not row:
                return None
            await conn.execute(
                """
                UPDATE "Job" SET status = 'working', progress = 'started', updated_at = NOW()
                WHERE id = $1
                """,
                row["id"],
            )
            uctx = row["user_context_json"]
            if isinstance(uctx, str):
                try:
                    uctx = json.loads(uctx)
                except (json.JSONDecodeError, TypeError):
                    uctx = None
            return {
                "id": row["id"],
                "project_id": row["project_id"],
                "user_id": row["user_id"],
                "question": row["question"],
                "user_context": uctx if isinstance(uctx, dict) else None,
                "job_kind": row["job_kind"] or "ask",
                "model_alias": row["model_alias"] or "smart",
                "audio_path": row["audio_path"],
            }


async def job_find_recent_duplicate(project_id: str, question_hash: str, within_seconds: int = 600) -> str | None:
    """Return job_id if a recent job with same project_id and question_hash exists."""
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM "Job"
            WHERE project_id = $1 AND question_hash = $2
              AND created_at > NOW() - ($3::text || ' seconds')::interval
            ORDER BY created_at DESC LIMIT 1
            """,
            project_id,
            question_hash,
            str(within_seconds),
        )
        return row["id"] if row else None


# --- Conversation History ---


async def conversation_append(user_id: str, project_id: str, role: str, content: str, job_id: str | None = None) -> str:
    """Append a message to the user's conversation history for a project."""
    msg_id = str(uuid4())
    async with (await get_pool()).acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversation_history (id, user_id, project_id, role, content, job_id, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            """,
            msg_id,
            user_id,
            project_id,
            role,
            content,
            job_id,
        )
    return msg_id


async def conversation_get_recent(user_id: str, project_id: str, limit: int = 10) -> list[dict]:
    """Get the last N messages for a user+project pair, ordered oldest-first."""
    async with (await get_pool()).acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content, created_at FROM conversation_history
            WHERE user_id = $1 AND project_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            user_id,
            project_id,
            limit,
        )
        return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in reversed(rows)]


async def conversation_delete(user_id: str, project_id: str) -> int:
    """Delete all conversation history for a user+project. Returns count deleted."""
    async with (await get_pool()).acquire() as conn:
        result = await conn.execute(
            "DELETE FROM conversation_history WHERE user_id = $1 AND project_id = $2",
            user_id,
            project_id,
        )
        return int(result.split()[-1])  # "DELETE N"


async def conversation_get_old_messages(user_id: str, project_id: str, before: datetime) -> list[dict]:
    """Get messages older than a date, oldest-first. Used for summarization."""
    async with (await get_pool()).acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, role, content, created_at FROM conversation_history
            WHERE user_id = $1 AND project_id = $2 AND created_at < $3
            ORDER BY created_at ASC
            """,
            user_id,
            project_id,
            before,
        )
        return [{"id": r["id"], "role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in rows]


async def conversation_delete_by_ids(ids: list[str]) -> int:
    """Delete specific conversation messages by ID."""
    if not ids:
        return 0
    async with (await get_pool()).acquire() as conn:
        result = await conn.execute(
            "DELETE FROM conversation_history WHERE id = ANY($1::text[])",
            ids,
        )
        return int(result.split()[-1])


# --- Conversation Summary ---


async def summary_upsert(user_id: str, project_id: str, period: str, summary: str, message_count: int) -> str:
    """Create or update a conversation summary for a user+project+period."""
    summary_id = str(uuid4())
    async with (await get_pool()).acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversation_summary (id, user_id, project_id, period, summary, message_count, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (user_id, project_id, period) DO UPDATE SET
                summary = EXCLUDED.summary,
                message_count = EXCLUDED.message_count
            """,
            summary_id,
            user_id,
            project_id,
            period,
            summary,
            message_count,
        )
    return summary_id


async def summary_get_recent(user_id: str, project_id: str, limit: int = 3) -> list[dict]:
    """Get the most recent N monthly summaries for a user+project, oldest-first."""
    async with (await get_pool()).acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT period, summary, message_count, created_at FROM conversation_summary
            WHERE user_id = $1 AND project_id = $2
            ORDER BY period DESC
            LIMIT $3
            """,
            user_id,
            project_id,
            limit,
        )
        return [{"period": r["period"], "summary": r["summary"], "message_count": r["message_count"]} for r in reversed(rows)]


# --- User Profile ---


async def user_profile_upsert(
    user_id: str,
    project_id: str,
    display_name: str | None = None,
    birth_date: datetime | None = None,
    notes: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Create or update a user profile for a project."""
    profile_id = str(uuid4())
    meta_json = json.dumps(metadata) if metadata else "{}"
    async with (await get_pool()).acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_profile (id, user_id, project_id, display_name, birth_date, notes, metadata, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW(), NOW())
            ON CONFLICT (user_id, project_id) DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, user_profile.display_name),
                birth_date = COALESCE(EXCLUDED.birth_date, user_profile.birth_date),
                notes = COALESCE(EXCLUDED.notes, user_profile.notes),
                metadata = user_profile.metadata || EXCLUDED.metadata,
                updated_at = NOW()
            """,
            profile_id,
            user_id,
            project_id,
            display_name,
            birth_date,
            notes,
            meta_json,
        )
    return profile_id


async def user_profile_get(user_id: str, project_id: str) -> dict | None:
    """Get the user profile for a project."""
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id, project_id, display_name, birth_date, notes, metadata, created_at, updated_at
            FROM user_profile
            WHERE user_id = $1 AND project_id = $2
            """,
            user_id,
            project_id,
        )
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "project_id": row["project_id"],
            "display_name": row["display_name"],
            "birth_date": row["birth_date"].isoformat() if row["birth_date"] else None,
            "notes": row["notes"],
            "metadata": row["metadata"] if row["metadata"] else {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


async def user_profile_delete(user_id: str, project_id: str) -> bool:
    """Delete a user profile. Returns True if deleted."""
    async with (await get_pool()).acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_profile WHERE user_id = $1 AND project_id = $2",
            user_id,
            project_id,
        )
        return int(result.split()[-1]) > 0


# --- Project CRUD ---


async def project_list_all() -> list[dict]:
    """List all projects."""
    async with (await get_pool()).acquire() as conn:
        rows = await conn.fetch(
            'SELECT id, project_id, name, sources, config_json, created_at, updated_at FROM "Project" ORDER BY created_at DESC'
        )
        return [
            {
                "id": r["id"],
                "project_id": r["project_id"],
                "name": r["name"],
                "sources": list(r["sources"]) if r["sources"] else [],
                "config_json": r["config_json"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]


async def project_create(
    project_id: str,
    name: str | None = None,
    sources: list[str] | None = None,
    config_json: dict | None = None,
) -> dict:
    pid = str(uuid4())
    cfg = json.dumps(config_json) if config_json else None
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO "Project" (id, project_id, name, sources, config_json, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, NOW(), NOW())
            RETURNING id, project_id, name, sources, config_json, created_at, updated_at
            """,
            pid,
            project_id,
            name,
            sources or [],
            cfg,
        )
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "sources": list(row["sources"]) if row["sources"] else [],
            "config_json": row["config_json"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


async def project_update(
    project_id: str,
    name: str | None = None,
    sources: list[str] | None = None,
    config_json: dict | None = None,
) -> dict:
    updates = ["updated_at = NOW()"]
    args: list = [project_id]
    idx = 2
    if name is not None:
        updates.append(f"name = ${idx}")
        args.append(name)
        idx += 1
    if sources is not None:
        updates.append(f"sources = ${idx}")
        args.append(sources)
        idx += 1
    if config_json is not None:
        updates.append(f"config_json = ${idx}::jsonb")
        args.append(json.dumps(config_json))
        idx += 1
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            f'UPDATE "Project" SET {", ".join(updates)} WHERE project_id = $1 RETURNING id, project_id, name, sources, config_json, created_at, updated_at',
            *args,
        )
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "sources": list(row["sources"]) if row["sources"] else [],
            "config_json": row["config_json"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


async def project_delete(project_id: str) -> None:
    async with (await get_pool()).acquire() as conn:
        await conn.execute('DELETE FROM "Project" WHERE project_id = $1', project_id)


async def project_themes_set(project_id: str, themes: list[str]) -> None:
    """Replace all themes for a project."""
    async with (await get_pool()).acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM project_themes WHERE project_id = $1", project_id)
            for theme in themes:
                await conn.execute(
                    "INSERT INTO project_themes (id, project_id, theme) VALUES ($1, $2, $3)",
                    str(uuid4()),
                    project_id,
                    theme,
                )


# --- Job Listing & Stats ---


async def job_list(
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List jobs with optional filters. Returns (jobs, total_count)."""
    where_clauses = []
    args: list = []
    idx = 1
    if project_id:
        where_clauses.append(f"project_id = ${idx}")
        args.append(project_id)
        idx += 1
    if status:
        where_clauses.append(f"status = ${idx}")
        args.append(status)
        idx += 1
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    async with (await get_pool()).acquire() as conn:
        count_row = await conn.fetchrow(
            f'SELECT COUNT(*) as cnt FROM "Job" {where_sql}',
            *args,
        )
        total = count_row["cnt"]

        rows = await conn.fetch(
            f"""
            SELECT id, project_id, question, status, progress, answer,
                   sources_json, confidence, error_message, created_at, updated_at,
                   job_kind, transcript
            FROM "Job" {where_sql}
            ORDER BY created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *args,
            limit,
            offset,
        )
        jobs = []
        for r in rows:
            jobs.append({
                "id": r["id"],
                "project_id": r["project_id"],
                "question": r["question"],
                "status": r["status"],
                "progress": r["progress"],
                "answer": r["answer"],
                "sources": _parse_sources(r["sources_json"]) if isinstance(r["sources_json"], str) else (r["sources_json"] or []),
                "confidence": r["confidence"],
                "error_message": r["error_message"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "job_kind": r["job_kind"] or "ask",
                "transcript": r["transcript"],
            })
        return jobs, total


async def job_stats() -> dict:
    """Aggregate job statistics."""
    async with (await get_pool()).acquire() as conn:
        total_row = await conn.fetchrow('SELECT COUNT(*) as cnt FROM "Job"')
        total = total_row["cnt"]

        status_rows = await conn.fetch('SELECT status, COUNT(*) as cnt FROM "Job" GROUP BY status')
        by_status = {r["status"]: r["cnt"] for r in status_rows}

        project_rows = await conn.fetch('SELECT project_id, COUNT(*) as cnt FROM "Job" GROUP BY project_id')
        by_project = {r["project_id"]: r["cnt"] for r in project_rows}

        last_24h_row = await conn.fetchrow(
            """SELECT COUNT(*) as cnt FROM "Job" WHERE created_at > NOW() - interval '24 hours'"""
        )
        last_24h = last_24h_row["cnt"]

        avg_row = await conn.fetchrow(
            """
            SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_sec
            FROM "Job"
            WHERE status IN ('done', 'no_answer', 'need_more_info')
              AND COALESCE(job_kind, 'ask') <> 'nabil_qualify_caption'
            """
        )
        avg_duration = round(float(avg_row["avg_sec"]), 2) if avg_row["avg_sec"] else None

    return {
        "total": total,
        "by_status": by_status,
        "by_project": by_project,
        "last_24h": last_24h,
        "avg_duration_seconds": avg_duration,
    }


async def job_cancel(job_id: str) -> None:
    async with (await get_pool()).acquire() as conn:
        await conn.execute(
            """UPDATE "Job" SET status = 'cancelled', updated_at = NOW() WHERE id = $1""",
            job_id,
        )

# --- API Keys ---


async def api_key_get_project_id(key_hash: str) -> str | None:
    """Find active project_id for a given API key hash."""
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE project_api_keys
            SET last_used_at = NOW()
            WHERE key_hash = $1 AND revoked_at IS NULL
            RETURNING project_id
            """,
            key_hash,
        )
        return row["project_id"] if row else None


async def api_key_create(project_id: str, key_hash: str, label: str | None = None) -> str:
    """Create a new API key for a project."""
    kid = str(uuid4())
    async with (await get_pool()).acquire() as conn:
        await conn.execute(
            """
            INSERT INTO project_api_keys (id, project_id, key_hash, label, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            kid,
            project_id,
            key_hash,
            label,
        )
    return kid


async def api_key_list(project_id: str) -> list[dict]:
    """List all API keys for a project."""
    async with (await get_pool()).acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, project_id, label, created_at, revoked_at, last_used_at
            FROM project_api_keys
            WHERE project_id = $1
            ORDER BY created_at DESC
            """,
            project_id,
        )
        return [dict(r) for r in rows]


async def api_key_revoke(key_id: str) -> None:
    """Revoke an API key."""
    async with (await get_pool()).acquire() as conn:
        await conn.execute(
            "UPDATE project_api_keys SET revoked_at = NOW() WHERE id = $1",
            key_id,
        )
