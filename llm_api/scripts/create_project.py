#!/usr/bin/env python3
"""
Bootstrap a new ai2tcs project: DB row, optional library template, API key.

Usage:
  python scripts/create_project.py my_project_2026 --name "My Project"
  python scripts/create_project.py my_project_2026 --library-root /path/to/content
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import shutil
import uuid
from pathlib import Path

import asyncpg

SCRIPT_DIR = Path(__file__).resolve().parent
LLM_ROOT = SCRIPT_DIR.parent
TEMPLATE_ROOT = LLM_ROOT / "project_library" / "_template"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def materialize_library(project_id: str, library_root: Path | None) -> list[str]:
    if library_root is not None:
        fluxos = library_root / "fluxosLLM"
        bib = library_root / "bibliotecaConteudoLLM"
        fluxos.mkdir(parents=True, exist_ok=True)
        bib.mkdir(parents=True, exist_ok=True)
        instr = fluxos / "instrucoes-llm.md"
        if not instr.exists():
            instr.write_text(
                f"# {project_id}\n\nAnswer in Portuguese. Be direct and helpful.\n",
                encoding="utf-8",
            )
        return [str(fluxos), str(bib)]

    dest = LLM_ROOT / "project_library" / project_id
    if dest.exists():
        fluxos = dest / "fluxosLLM"
        bib = dest / "bibliotecaConteudoLLM"
    else:
        if TEMPLATE_ROOT.exists():
            shutil.copytree(TEMPLATE_ROOT, dest)
        else:
            dest.mkdir(parents=True)
            (dest / "fluxosLLM").mkdir()
            (dest / "bibliotecaConteudoLLM").mkdir()
            (dest / "fluxosLLM" / "instrucoes-llm.md").write_text(
                f"# {project_id}\n\nAnswer in Portuguese. Be direct and helpful.\n",
                encoding="utf-8",
            )
        fluxos = dest / "fluxosLLM"
        bib = dest / "bibliotecaConteudoLLM"
    return [str(fluxos), str(bib)]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create ai2tcs project + API key")
    parser.add_argument("project_id")
    parser.add_argument("--name", help="Display name (defaults to project_id)")
    parser.add_argument("--library-root", type=Path, help="Existing folder to use as library root")
    parser.add_argument("--profile", default="factual", choices=("factual", "sales", "creative"))
    parser.add_argument("--no-key", action="store_true", help="Skip API key creation")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "postgresql://localhost:5432/llmapi"),
    )
    args = parser.parse_args()

    sources = materialize_library(args.project_id, args.library_root)
    config_json = {
        "prompt_profile": args.profile,
        "behavior_instruction_path": "instrucoes-llm.md",
        "chunking": {"chunk_size": 512, "chunk_overlap": 64, "separator": "\n\n"},
        "embedding_model": "mxbai-embed-large",
        "policies": {
            "rag_mode": "required",
            "max_chunks_to_retrieve": 5,
            "max_chunk_distance": 1.0,
            "dedup_ttl_seconds": 600,
        },
        "llm_options": {
            "temperature": 0.5,
            "message_size": "medium",
            "tone_of_voice": "direct",
        },
        "router": {
            "routes": ["ask", "cadastro", "saudacao", "escalar_humano"],
            "extra_system_block": "",
            "default_escalate_model": "smart",
        },
    }

    conn = await asyncpg.connect(args.database_url)
    raw_key: str | None = None
    try:
        pid = str(uuid.uuid4())
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
            pid,
            args.project_id,
            args.name or args.project_id,
            sources,
            json.dumps(config_json),
        )
        if not args.no_key:
            raw_key = f"itcs_{args.project_id}_{secrets.token_hex(12)}"
            await conn.execute(
                """
                INSERT INTO project_api_keys (id, project_id, key_hash, label, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                """,
                str(uuid.uuid4()),
                args.project_id,
                hash_key(raw_key),
                "create_project_cli",
            )
    finally:
        await conn.close()

    print(f"Project: {args.project_id}")
    print(f"Sources: {sources}")
    print("Next steps:")
    print(f"  1. POST /ingest  body={{\"project_id\": \"{args.project_id}\"}}")
    print(f"  2. POST /ask     body={{\"project_id\": \"{args.project_id}\", \"question\": \"...\"}}")
    if raw_key:
        print(f"API key (save now): {raw_key}")


if __name__ == "__main__":
    asyncio.run(main())
