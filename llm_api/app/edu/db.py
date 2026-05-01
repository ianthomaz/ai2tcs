"""DB helpers for educational tables (edu_*)."""
import json
from uuid import UUID
from app.db import get_pool

async def vocab_list(language: str = "zh-CN", level: str = None, limit: int = 50, offset: int = 0):
    async with (await get_pool()).acquire() as conn:
        where = "WHERE language = $1"
        args = [language]
        if level:
            where += " AND level = $2"
            args.append(level)

        count_row = await conn.fetchrow(f'SELECT COUNT(*) FROM edu_vocabulary {where}', *args)
        total = count_row[0]

        rows = await conn.fetch(
            f'SELECT * FROM edu_vocabulary {where} ORDER BY created_at DESC LIMIT ${len(args)+1} OFFSET ${len(args)+2}',
            *args, limit, offset
        )
        return [dict(r) for r in rows], total

async def vocab_get(vocab_id: str):
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM edu_vocabulary WHERE id = $1', UUID(vocab_id))
        return dict(row) if row else None

async def vocab_get_many(vocab_ids: list[str]):
    if not vocab_ids:
        return []
    async with (await get_pool()).acquire() as conn:
        rows = await conn.fetch('SELECT * FROM edu_vocabulary WHERE id = ANY($1::uuid[])', [UUID(vid) for vid in vocab_ids])
        return [dict(r) for r in rows]

async def vocab_create(data: dict):
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO edu_vocabulary (
                language, hanzi, pinyin, translation, level, category,
                example_sentence, example_pinyin, example_translation
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            data.get("language", "zh-CN"), data["hanzi"], data["pinyin"], data["translation"],
            data["level"], data.get("category"), data.get("example_sentence"),
            data.get("example_pinyin"), data.get("example_translation")
        )
        return dict(row)

async def grammar_list(language: str = "zh-CN", level: str = None, limit: int | None = None):
    async with (await get_pool()).acquire() as conn:
        where = "WHERE language = $1"
        args = [language]
        if level:
            where += " AND level = $2"
            args.append(level)

        count_row = await conn.fetchrow(f'SELECT COUNT(*) FROM edu_grammar {where}', *args)
        total = count_row[0]

        lim_sql = ""
        if limit is not None and limit > 0:
            args.append(limit)
            lim_sql = f" LIMIT ${len(args)}"

        rows = await conn.fetch(
            f'SELECT * FROM edu_grammar {where} ORDER BY created_at DESC{lim_sql}',
            *args,
        )
        return [dict(r) for r in rows], total

async def grammar_create(data: dict):
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO edu_grammar (language, pattern, explanation, level, examples)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            data.get("language", "zh-CN"), data["pattern"], data["explanation"],
            data["level"], json.dumps(data.get("examples", []))
        )
        return dict(row)

async def progress_upsert(user_id: str, vocab_id: str, correct: bool):
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO edu_progress (user_id, vocab_id, seen_count, correct_count, last_seen, mastered)
            VALUES ($1, $2, 1, $3, NOW(), FALSE)
            ON CONFLICT (user_id, vocab_id) DO UPDATE SET
                seen_count = edu_progress.seen_count + 1,
                correct_count = edu_progress.correct_count + $3,
                last_seen = NOW(),
                mastered = CASE WHEN (edu_progress.correct_count + $3) >= 5 THEN TRUE ELSE FALSE END
            RETURNING *
            """,
            user_id, UUID(vocab_id), 1 if correct else 0
        )
        return dict(row)

async def progress_get_for_user(user_id: str):
    async with (await get_pool()).acquire() as conn:
        rows = await conn.fetch('SELECT * FROM edu_progress WHERE user_id = $1', user_id)
        return [dict(r) for r in rows]
