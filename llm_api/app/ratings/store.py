"""Database side of the ratings door: answer_ratings and rating_proposals."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app import db as db_module
from app.ratings.logic import add_forbidden_term


def _ts(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


async def save(project_id: str, item: dict[str, Any]) -> None:
    """Upsert by (project_id, source_ref); `rating: None` deletes the row."""
    async with (await db_module.get_pool()).acquire() as conn:
        if item["rating"] is None:
            await conn.execute(
                'DELETE FROM "answer_ratings" WHERE project_id = $1 AND source_ref = $2',
                project_id, item["source_ref"],
            )
            return
        await conn.execute(
            """
            INSERT INTO "answer_ratings" (project_id, source_ref, question, answer, rating, reason, signals, rated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
            ON CONFLICT (project_id, source_ref) DO UPDATE SET
                question = EXCLUDED.question, answer = EXCLUDED.answer, rating = EXCLUDED.rating,
                reason = EXCLUDED.reason, signals = EXCLUDED.signals, rated_at = EXCLUDED.rated_at,
                received_at = CURRENT_TIMESTAMP
            """,
            project_id, item["source_ref"], item["question"], item["answer"], item["rating"],
            item["reason"], json.dumps(item["signals"]) if item["signals"] is not None else None,
            _ts(item["rated_at"]),
        )


async def propose(project_id: str, kind: str, value: str, source_ref: str) -> bool:
    """New pending proposal, or the source added to an existing one. True when it is new."""
    async with (await db_module.get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO "rating_proposals" (project_id, kind, value, source_refs)
            VALUES ($1, $2, $3, ARRAY[$4]::text[])
            ON CONFLICT (project_id, kind, value) DO UPDATE SET source_refs =
                CASE WHEN $4 = ANY("rating_proposals".source_refs) THEN "rating_proposals".source_refs
                     ELSE array_append("rating_proposals".source_refs, $4) END
            RETURNING (xmax = 0) AS inserted
            """,
            project_id, kind, value, source_ref,
        )
        return bool(row and row["inserted"])


def _proposal(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "value": row["value"],
        "source_refs": list(row["source_refs"] or []),
        "status": row["status"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "decided_at": row["decided_at"].isoformat() if row["decided_at"] else None,
        "decided_by": row["decided_by"],
    }


async def list_proposals(project_id: str, status: str | None) -> list[dict[str, Any]]:
    async with (await db_module.get_pool()).acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, kind, value, source_refs, status, created_at, decided_at, decided_by
            FROM "rating_proposals" WHERE project_id = $1 AND ($2::text IS NULL OR status = $2)
            ORDER BY created_at DESC LIMIT 500
            """,
            project_id, status,
        )
        return [_proposal(r) for r in rows]


async def decide(project_id: str, proposal_id: int, approve: bool, decided_by: str | None) -> dict[str, Any] | None:
    """Approve or reject a pending proposal. Approving a forbidden_term adds it to the project's
    policies.forbidden_terms in the same transaction. None when there is no pending proposal."""
    pool = await db_module.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE "rating_proposals" SET status = $3, decided_at = CURRENT_TIMESTAMP, decided_by = $4
                WHERE id = $1 AND project_id = $2 AND status = 'pending'
                RETURNING id, kind, value, source_refs, status, created_at, decided_at, decided_by
                """,
                proposal_id, project_id, "approved" if approve else "rejected", decided_by,
            )
            if row is None:
                return None
            if approve and row["kind"] == "forbidden_term":
                cfg = await conn.fetchval(
                    'SELECT config_json FROM "Project" WHERE project_id = $1 FOR UPDATE', project_id
                )
                if isinstance(cfg, str):
                    cfg = json.loads(cfg)
                await conn.execute(
                    'UPDATE "Project" SET config_json = $2::jsonb, updated_at = NOW() WHERE project_id = $1',
                    project_id, json.dumps(add_forbidden_term(cfg, row["value"])),
                )
            return _proposal(row)


async def great_examples(project_id: str, limit: int = 200) -> list[dict[str, Any]]:
    async with (await db_module.get_pool()).acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT question, answer FROM "answer_ratings"
            WHERE project_id = $1 AND rating = 'great' ORDER BY received_at DESC LIMIT $2
            """,
            project_id, limit,
        )
        return [{"question": r["question"], "answer": r["answer"]} for r in rows]
