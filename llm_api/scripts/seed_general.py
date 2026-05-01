"""Seed the 'general' project: a free-form assistant with no RAG requirement.

Usage:
    python scripts/seed_general.py

The 'general' project is designed for open-ended semantic questions that don't
belong to any specific domain. RAG is disabled so the LLM answers directly from
its training knowledge — useful for quick lookups, reasoning, brainstorming, etc.

To use with a specific model, pass __llm_model in user_context:
    POST /ask  { "project_id": "general", "question": "...", "model": "reasoner" }
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/llmapi")

PROJECT_ID = "general"

CONFIG = {
    "llm_provider": "ollama",
    "policies": {
        "rag_mode": "disabled",
        "when_no_answer": "done",
    },
    "llm_options": {
        "temperature": 0.65,
        "top_k": 40,
        "top_p": 0.92,
        "repeat_penalty": 1.1,
        "num_predict": 2048,
        "tone_of_voice": "direct",
        "message_size": "medium",
    },
    "system_instruction": (
        "Você é um assistente pessoal inteligente. "
        "Responda em português do Brasil de forma direta e precisa. "
        "Pode responder qualquer pergunta: raciocínio, código, escrita, pesquisa, análise, criatividade. "
        "Não há base de conhecimento vinculada — use seu conhecimento geral. "
        "Se não souber com certeza, diga explicitamente em vez de inventar."
    ),
}

SQL_UPSERT = """
INSERT INTO "Project" ("projectId", name, sources, "configJson", "createdAt", "updatedAt")
VALUES ($1, $2, $3, $4::jsonb, NOW(), NOW())
ON CONFLICT ("projectId") DO UPDATE
  SET name       = EXCLUDED.name,
      "configJson" = EXCLUDED."configJson",
      "updatedAt"  = NOW()
RETURNING "projectId", name;
"""

import json


async def seed():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            SQL_UPSERT,
            PROJECT_ID,
            "Assistente Geral",
            [],
            json.dumps(CONFIG),
        )
        print(f"✓ Project upserted: {row['projectId']} — {row['name']}")
        print()
        print("Config aplicado:")
        print(f"  rag_mode    : disabled  (sem biblioteca, responde diretamente)")
        print(f"  provider    : ollama    (padrão local)")
        print(f"  temperature : 0.65      (um pouco mais criativo que os projetos RAG)")
        print(f"  num_predict : 2048      (respostas mais longas permitidas)")
        print()
        print("Uso:")
        print('  POST /ask  {"project_id": "general", "question": "Explica gradient descent"}')
        print('  POST /ask  {"project_id": "general", "question": "...", "model": "reasoner"}')
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
