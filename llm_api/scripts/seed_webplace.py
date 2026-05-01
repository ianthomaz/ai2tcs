#!/usr/bin/env python3
"""
Seed project webplace — internal dev, batch normalization, local RAG library.

Default sources live under llm_api/project_library/webplace/ (fluxosLLM first so
instrucoes-llm.md is resolved from behavior_instruction_path).

Override: WEBPLACE_SOURCES=comma-separated absolute paths (two folders recommended).

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
DEFAULT_WEBPLACE_ROOT = FEATURE_LLM_ROOT / "project_library" / "webplace"


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/llmapi")
    conn = await asyncpg.connect(database_url)
    try:
        project_id = "webplace"
        sources_raw = os.environ.get("WEBPLACE_SOURCES", "").strip()
        if sources_raw:
            sources = [p.strip() for p in sources_raw.split(",") if p.strip()]
        else:
            sources = [
                str(DEFAULT_WEBPLACE_ROOT / "fluxosLLM"),
                str(DEFAULT_WEBPLACE_ROOT / "bibliotecaConteudoLLM"),
            ]
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
            "Webplace (internal dev & data tools)",
            sources,
            json.dumps(
                {
                    "behavior_instruction_path": "instrucoes-llm.md",
                    "chunking": {"chunk_size": 512, "chunk_overlap": 64, "separator": "\n\n"},
                    "embedding_model": "nomic-embed-text",
                    "policies": {
                        "prefer_cite_sources": False,
                        "when_no_answer": "no_answer",
                        "max_chunks_to_retrieve": 3,
                        "max_chunk_distance": 1.05,
                        "search_depth": "standard",
                    },
                    "llm_options": {
                        "temperature": 0.2,
                        "num_predict": 640,
                        "top_k": 24,
                        "top_p": 0.88,
                        "repeat_penalty": 1.12,
                        "message_size": "short",
                        "tone_of_voice": "technical",
                    },
                }
            ),
        )
        for theme in ("webplace", "dev", "internal"):
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
        print("Seeded project webplace.")
        print(f"  sources: {sources}")
        print("  Optional override: WEBPLACE_SOURCES=path1,path2")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
