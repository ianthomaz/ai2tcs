#!/usr/bin/env python3
"""
Seed project ian_zap — Ian personal WhatsApp (LLM mode + router; Cursor via :28472).

Run after migrations:
  ZAPCURSOR_DOCS_ROOT=/Users/ianthomaz/Documents/projects/zapCursorAgent \
  python3 llm_api/scripts/seed_ian_zap.py

API key: Dashboard → Projetos → ian_zap → Chaves API (itcs_ian_zap_…).
"""
import asyncio
import json
import os
import uuid

import asyncpg

# RAG library at repo root — NOT repo docs/ (that is developer documentation)
LIBRARY_DIR = "bibliotecaLLM_ian_zap"


async def main():
    database_url = os.environ.get("DATABASE_URL", "postgresql://llmapi:llmapi_dev@localhost:5437/llmapi")
    root = os.environ.get(
        "ZAPCURSOR_REPO_ROOT",
        os.environ.get(
            "ZAPCURSOR_DOCS_ROOT",
            os.path.expanduser("~/Documents/projects/zapCursorAgent"),
        ),
    ).strip()
    sources = [os.path.join(root, LIBRARY_DIR)] if root else []

    conn = await asyncpg.connect(database_url)
    try:
        project_id = "ian_zap"
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
            "Ian — Zap pessoal",
            sources,
            json.dumps(
                {
                    "chunking": {"chunk_size": 512, "chunk_overlap": 64, "separator": "\n\n"},
                    "embedding_model": "mxbai-embed-large",
                    "policies": {
                        "prefer_cite_sources": True,
                        "when_no_answer": "no_answer",
                        "max_chunks_to_retrieve": 6,
                    },
                    "llm_options": {
                        "temperature": 0.4,
                        "num_predict": 1024,
                    },
                }
            ),
        )
        for theme in ("zap", "cursor", "infra"):
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
        print("Seeded project ian_zap.")
        print("  sources:", sources)
        print("  Next: dashboard API key + ingest sources if needed")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
