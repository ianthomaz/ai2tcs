"""Database side of the second opinion queue (table second_opinions)."""
from __future__ import annotations

import json
from typing import Any

from app import db as db_module

STALE_WORKING_MINUTES = 10


def _row(r: Any) -> dict[str, Any]:
    def js(v):
        return json.loads(v) if isinstance(v, str) else v

    return {
        "id": r["id"],
        "project_id": r["project_id"],
        "source_ref": r["source_ref"],
        "channel": r["channel"],
        "case_kind": r["case_kind"],
        "status": r["status"],
        "request": js(r["request"]),
        "response": js(r["response"]),
        "agent": r["agent"],
        "error": r["error"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
    }


_COLS = "id, project_id, source_ref, channel, case_kind, status, request, response, agent, error, created_at, finished_at"


async def enqueue(project_id: str, case: dict[str, Any], daily_limit: int) -> tuple[str, dict[str, Any] | None]:
    """('queued' | 'exists' | 'limit', row). The daily limit counts every case accepted today,
    all projects together, inside the same transaction as the insert."""
    pool = await db_module.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('second_opinions_daily'))")
            existing = await conn.fetchrow(
                f'SELECT {_COLS} FROM "second_opinions" WHERE project_id = $1 AND source_ref = $2',
                project_id, case["source_ref"],
            )
            if existing:
                return "exists", _row(existing)
            today = await conn.fetchval('SELECT COUNT(*) FROM "second_opinions" WHERE created_at >= CURRENT_DATE')
            if today >= daily_limit:
                return "limit", None
            row = await conn.fetchrow(
                f"""INSERT INTO "second_opinions" (project_id, source_ref, channel, case_kind, request)
                    VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING {_COLS}""",
                project_id, case["source_ref"], case["channel"], case["case_kind"],
                json.dumps(case, ensure_ascii=False),
            )
            return "queued", _row(row)


async def get(project_id: str, source_ref: str) -> dict[str, Any] | None:
    async with (await db_module.get_pool()).acquire() as conn:
        r = await conn.fetchrow(
            f'SELECT {_COLS} FROM "second_opinions" WHERE project_id = $1 AND source_ref = $2', project_id, source_ref
        )
        return _row(r) if r else None


async def claim() -> dict[str, Any] | None:
    """Oldest queued case (or one stuck in `working`), marked working. None when the queue is empty."""
    async with (await db_module.get_pool()).acquire() as conn:
        r = await conn.fetchrow(
            f"""UPDATE "second_opinions" SET status = 'working', claimed_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM "second_opinions"
                    WHERE status = 'queued'
                       OR (status = 'working' AND claimed_at < CURRENT_TIMESTAMP - ($1 * INTERVAL '1 minute'))
                    ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
                ) RETURNING {_COLS}""",
            STALE_WORKING_MINUTES,
        )
        return _row(r) if r else None


async def get_working(case_id: int) -> dict[str, Any] | None:
    async with (await db_module.get_pool()).acquire() as conn:
        r = await conn.fetchrow(f'SELECT {_COLS} FROM "second_opinions" WHERE id = $1 AND status = \'working\'', case_id)
        return _row(r) if r else None


async def finish(case_id: int, agent: str, response: dict[str, Any] | None, error: str | None) -> bool:
    async with (await db_module.get_pool()).acquire() as conn:
        done = await conn.fetchval(
            """UPDATE "second_opinions" SET status = $2, response = $3::jsonb, agent = $4, error = $5,
                      finished_at = CURRENT_TIMESTAMP
               WHERE id = $1 AND status = 'working' RETURNING id""",
            case_id, "done" if response is not None else "failed",
            json.dumps(response, ensure_ascii=False) if response is not None else None, agent[:60], error,
        )
        return done is not None


async def stats(project_id: str, days: int) -> list[dict[str, Any]]:
    """Per case_kind: how the teacher rated the local answer. Falling `bad`/`wrong` over time is
    the local model needing the teacher less."""
    async with (await db_module.get_pool()).acquire() as conn:
        rows = await conn.fetch(
            """SELECT COALESCE(case_kind, '-') AS case_kind, date_trunc('week', created_at) AS week,
                      COUNT(*) FILTER (WHERE status = 'done')::int AS done,
                      COUNT(*) FILTER (WHERE status = 'failed')::int AS failed,
                      COUNT(*) FILTER (WHERE response->>'local_answer_rating' IN ('good', 'great'))::int AS local_good,
                      COUNT(*) FILTER (WHERE response->>'local_answer_rating' IN ('bad', 'stop'))::int AS local_bad,
                      COUNT(*) FILTER (WHERE response->>'local_answer_path' = 'wrong')::int AS path_wrong
               FROM "second_opinions"
               WHERE project_id = $1 AND created_at >= CURRENT_TIMESTAMP - ($2 * INTERVAL '1 day')
               GROUP BY 1, 2 ORDER BY 2 DESC, 1""",
            project_id, days,
        )
        return [{**dict(r), "week": r["week"].date().isoformat()} for r in rows]


async def queue_depth() -> dict[str, Any]:
    """Waiting / in-flight counts for /health and /metrics. Stale `working` rows are reclaimable
    by `claim()` after STALE_WORKING_MINUTES."""
    async with (await db_module.get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """SELECT
                 COUNT(*) FILTER (WHERE status = 'queued')::int AS queued,
                 COUNT(*) FILTER (WHERE status = 'working')::int AS working,
                 COUNT(*) FILTER (
                   WHERE status = 'working'
                     AND claimed_at < CURRENT_TIMESTAMP - ($1 * INTERVAL '1 minute')
                 )::int AS working_stale,
                 EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at) FILTER (WHERE status = 'queued')))
                   AS oldest_queued_age_seconds
               FROM "second_opinions"
               WHERE status IN ('queued', 'working')""",
            STALE_WORKING_MINUTES,
        )
    oldest = row["oldest_queued_age_seconds"]
    return {
        "queued": int(row["queued"] or 0),
        "working": int(row["working"] or 0),
        "working_stale": int(row["working_stale"] or 0),
        "oldest_queued_age_seconds": int(oldest) if oldest is not None else None,
        "stale_working_minutes": STALE_WORKING_MINUTES,
    }
