#!/usr/bin/env python3
"""
Seed project bikeanjoall_2026. Run after Prisma migrations.
Library paths: set BIKEANJOALL_2026_SOURCES in .env (comma-separated) or they default to a placeholder.
"""
import asyncio
import json
import os
import uuid

import asyncpg


async def main():
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/llmapi")
    conn = await asyncpg.connect(database_url)
    try:
        project_id = "bikeanjoall_2026"
        sources_raw = os.environ.get("BIKEANJOALL_2026_SOURCES", "")
        sources = [p.strip() for p in sources_raw.split(",") if p.strip()] if sources_raw else []
        if not sources:
            sources = ["/placeholder/bikeanjoall_2026/content"]
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
            "Bike Anjo 2026 (site + PDFs)",
            sources,
            json.dumps({
                "chunking": {"chunk_size": 512, "chunk_overlap": 64, "separator": "\n\n"},
                "embedding_model": "nomic-embed-text",
                "policies": {"prefer_cite_sources": True, "when_no_answer": "no_answer", "max_chunks_to_retrieve": 5},
            }),
        )
        for theme in ("bikeanjo", "institucional"):
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
        print("Seeded project bikeanjoall_2026. Set BIKEANJOALL_2026_SOURCES in .env for real paths.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
