#!/usr/bin/env python3
"""
Seed project aiclaudia — creative chatbot (033_aiClaudia RAG library).

Default sources: sibling repo 033_aiClaudia/rag/ (six markdown files).

Override: AICLAUDIA_SOURCES=comma-separated absolute paths.

Run after Prisma migrations, with DATABASE_URL pointing at the API Postgres.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import asyncpg

SCRIPT_DIR = Path(__file__).resolve().parent
FEATURE_LLM_ROOT = SCRIPT_DIR.parent
DEFAULT_AICLAUDIA_RAG = Path("/Users/ianthomaz/Documents/projects/033_aiClaudia/rag")


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/llmapi")
    conn = await asyncpg.connect(database_url)
    try:
        project_id = "aiclaudia"
        sources_raw = os.environ.get("AICLAUDIA_SOURCES", "").strip()
        if sources_raw:
            sources = [p.strip() for p in sources_raw.split(",") if p.strip()]
        else:
            sources = [str(DEFAULT_AICLAUDIA_RAG)]
        id_ = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO "Project" (id, project_id, name, sources, config_json, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
            ON CONFLICT (project_id) DO UPDATE SET
                name = EXCLUDED.name,
                sources = EXCLUDED.sources,
                config_json = EXCLUDED.config_json,
                updated_at = NOW()
            """,
            id_,
            project_id,
            "aiClaudia (creative cloud personas)",
            sources,
            json.dumps(
                {
                    "prompt_profile": "creative",
                    "no_answer_fallback": (
                        "Responda com humor surreal em uma frase curta, mantendo a persona da sessão."
                    ),
                    "chunking": {"chunk_size": 512, "chunk_overlap": 64, "separator": "\n\n"},
                    "embedding_model": "mxbai-embed-large",
                    "policies": {
                        "prefer_cite_sources": False,
                        "when_no_answer": "allow_model",
                        "rag_mode": "optional",
                        "max_chunks_to_retrieve": 4,
                        "max_chunk_distance": 1.1,
                        "search_depth": "standard",
                        "dedup_ttl_seconds": 0,
                    },
                    "llm_options": {
                        "temperature": 0.85,
                        "num_predict": 400,
                        "top_k": 40,
                        "top_p": 0.92,
                        "repeat_penalty": 1.15,
                        "message_size": "short",
                        "tone_of_voice": "informal",
                    },
                }
            ),
        )
        for theme in ("creative", "humor", "personas"):
            await conn.execute(
                """
                INSERT INTO project_themes (id, project_id, theme)
                VALUES ($1, $2, $3)
                ON CONFLICT (project_id, theme) DO NOTHING
                """,
                str(uuid.uuid4()),
                project_id,
                theme,
            )
        print("Seeded project aiclaudia.")
        print(f"  sources: {sources}")
        print("  Optional override: AICLAUDIA_SOURCES=path1,path2")
        print("  Next: POST /ingest with project_id=aiclaudia")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
