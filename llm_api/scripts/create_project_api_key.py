#!/usr/bin/env python3
"""Create a project API key (same format as dashboard). Prints raw key once to stdout."""
import argparse
import asyncio
import hashlib
import os
import secrets
import sys
import uuid

import asyncpg


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id")
    parser.add_argument("--label", default="bootstrap")
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL", "postgresql://llmapi:llmapi_dev@localhost:5437/llmapi"
        ),
    )
    args = parser.parse_args()

    raw_key = f"itcs_{args.project_id}_{secrets.token_hex(12)}"
    key_hash = hash_key(raw_key)

    conn = await asyncpg.connect(args.database_url)
    try:
        row = await conn.fetchrow(
            'SELECT 1 FROM "Project" WHERE project_id = $1', args.project_id
        )
        if not row:
            print(f"Project {args.project_id} not found — run seed first.", file=sys.stderr)
            sys.exit(1)
        await conn.execute(
            """
            INSERT INTO project_api_keys (id, project_id, key_hash, label, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            str(uuid.uuid4()),
            args.project_id,
            key_hash,
            args.label,
        )
    finally:
        await conn.close()

    print(raw_key)


if __name__ == "__main__":
    asyncio.run(main())
