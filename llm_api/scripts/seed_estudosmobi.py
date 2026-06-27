#!/usr/bin/env python3
"""
Seed project estudosmobi — Mobi contabilidade RAG library.

Default sources (fluxosLLM first for instrucoes-llm.md resolution):
  estudosMobi/fluxosLLM, estudosMobi/bibliotecaConteudoLLM

Override: ESTUDOSMOBI_SOURCES=comma-separated absolute paths.

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
DEFAULT_ESTUDOSMOBI_ROOT = Path("/Users/ianthomaz/Documents/projects/estudosMobi")


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/llmapi")
    conn = await asyncpg.connect(database_url)
    try:
        project_id = "estudosmobi"
        sources_raw = os.environ.get("ESTUDOSMOBI_SOURCES", "").strip()
        if sources_raw:
            sources = [p.strip() for p in sources_raw.split(",") if p.strip()]
        else:
            sources = [
                str(DEFAULT_ESTUDOSMOBI_ROOT / "fluxosLLM"),
                str(DEFAULT_ESTUDOSMOBI_ROOT / "bibliotecaConteudoLLM"),
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
            "Estudos Mobi (contabilidade)",
            sources,
            json.dumps(
                {
                    "prompt_profile": "sales",
                    "no_answer_fallback": (
                        "A Mobi cuida disso para você — fale com a equipe pelo WhatsApp ou acesse mobicontabil.com.br."
                    ),
                    "behavior_instruction_path": "instrucoes-llm.md",
                    "chunking": {"chunk_size": 512, "chunk_overlap": 64, "separator": "\n\n"},
                    "embedding_model": "mxbai-embed-large",
                    "policies": {
                        "prefer_cite_sources": True,
                        "when_no_answer": "no_answer",
                        "rag_mode": "required",
                        "max_chunks_to_retrieve": 5,
                        "max_chunk_distance": 0.9,
                        "search_depth": "standard",
                        "dedup_ttl_seconds": 600,
                    },
                    "llm_options": {
                        "temperature": 0.45,
                        "num_predict": 1024,
                        "top_k": 30,
                        "top_p": 0.9,
                        "repeat_penalty": 1.35,
                        "message_size": "medium",
                        "tone_of_voice": "sales",
                    },
                }
            ),
        )
        for theme in ("contabilidade", "mei", "empresa", "impostos", "mobi"):
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
        print("Seeded project estudosmobi.")
        print(f"  sources: {sources}")
        print("  Optional override: ESTUDOSMOBI_SOURCES=path1,path2")
        print("  Next: POST /ingest with project_id=estudosmobi")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
