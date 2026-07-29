#!/usr/bin/env python3
"""
Seed project webplacecc. Run after Prisma migrations.

Single path (recommended): set WEBPLACECC_ROOT to the project root; the script derives
sources from root/bibliotecaLLM_webplacecc and root/mapaFluxosLLM.

Alternatively: set WEBPLACECC_SOURCES to a comma-separated list of folder paths.
"""
import asyncio
import json
import os
import uuid

import asyncpg

# Subfolder names under project root (when using WEBPLACECC_ROOT)
LIBRARY_DIR = "bibliotecaLLM_webplacecc"
MAPA_FLUXOS_DIR = "mapaFluxosLLM"


async def main():
    database_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/llmapi")
    conn = await asyncpg.connect(database_url)
    try:
        project_id = "webplacecc"
        root = os.environ.get("WEBPLACECC_ROOT", "").strip()
        if root:
            # Single path: derive the two source folders from project root
            sources = [
                os.path.join(root, LIBRARY_DIR),
                os.path.join(root, MAPA_FLUXOS_DIR),
            ]
        else:
            sources_raw = os.environ.get("WEBPLACECC_SOURCES", "")
            sources = [p.strip() for p in sources_raw.split(",") if p.strip()] if sources_raw else []
        if not sources:
            sources = ["/placeholder/webplacecc/bibliotecaLLM_webplacecc"]
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
            "webplace.cc (zap + site)",
            sources,
            json.dumps({
                "chunking": {"chunk_size": 512, "chunk_overlap": 64, "separator": "\n\n"},
                "embedding_model": "mxbai-embed-large",
                "policies": {"prefer_cite_sources": True, "when_no_answer": "no_answer", "max_chunks_to_retrieve": 8},
                "llm_options": {
                    "tone_of_voice": "friendly",
                    "message_size": "short",
                    "temperature": 0.3,
                },
            }),
        )
        for theme in ("webplace", "zap"):
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
        print("Seeded project webplacecc.")
        print("  Use WEBPLACECC_ROOT=/path/to/webplacecc (single path) or WEBPLACECC_SOURCES=folder1,folder2")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
