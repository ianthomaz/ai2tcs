#!/usr/bin/env python3
"""
Seed project bikeanjoall_2026. Run after Prisma migrations.
Library paths: set BIKEANJOALL_2026_SOURCES in .env (comma-separated) or they default to a placeholder.
"""
import asyncio
import json
import os
import uuid
from pathlib import Path

import asyncpg

# Forma e postura da resposta (não conteúdo), na pasta do projeto: o system prompt do /ask
# termina com postura-ask.md (vence as regras genéricas anteriores); o roteador recebe
# postura-router.md (o ROUTER_SYSTEM genérico pede resposta "friendly", o oposto do corpus).
_DIRETRIZES = Path(__file__).resolve().parents[1] / "project_library" / "bikeanjoall_2026" / "diretrizes"
BIKEANJO_SYSTEM_INSTRUCTION = (_DIRETRIZES / "postura-ask.md").read_text(encoding="utf-8")
BIKEANJO_ROUTER_BLOCK = (_DIRETRIZES / "postura-router.md").read_text(encoding="utf-8")


# Retrieval hints of the bot channel, from the Bike Anjo contract (contracts/bikeanjo/rag/).
_HINTS_FILE = Path(__file__).resolve().parents[1] / "contracts" / "bikeanjo" / "rag" / "retrieval-hints.json"


def bot_retrieval_hints() -> dict:
    """config_json.retrieval_hints for /ask and /router: the contract's `ask` port + intent clusters."""
    raw = json.loads(_HINTS_FILE.read_text(encoding="utf-8"))
    ask = {k: v for k, v in (raw.get("ports") or {}).get("ask", {}).items()
           if k in ("boost_path_substrings", "downrank_path_substrings", "exclude_path_substrings")}
    clusters = {name: {k: v for k, v in c.items() if k in ("keywords", "boost_path_substrings", "extra_downrank")}
                for name, c in (raw.get("intent_clusters") or {}).items()}
    return {"ports": {"ask": ask}, "intent_clusters": clusters}


async def keep_approved_terms(conn, project_id: str, config: dict) -> dict:
    """The seed config plus the forbidden terms people approved in /ratings (docs/22).

    The seed replaces config_json whole; without this, re-running it would drop every term
    approved in the Bike Anjo panel.
    """
    try:
        rows = await conn.fetch(
            """SELECT value FROM "rating_proposals"
               WHERE project_id = $1 AND kind = 'forbidden_term' AND status = 'approved'""",
            project_id,
        )
    except asyncpg.UndefinedTableError:
        rows = []
    terms = list(config["policies"].get("forbidden_terms") or [])
    known = {t.lower() for t in terms}
    for r in rows:
        if r["value"].lower() not in known:
            terms.append(r["value"])
            known.add(r["value"].lower())
    config["policies"]["forbidden_terms"] = terms
    return config


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
            json.dumps(await keep_approved_terms(conn, project_id, {
                "chunking": {"chunk_size": 512, "chunk_overlap": 64, "separator": "\n\n"},
                "embedding_model": "mxbai-embed-large",
                # /ask and /router reorder the search by these (app/rag/hints.py).
                "retrieval_hints": bot_retrieval_hints(),
                "policies": {
                    "prefer_cite_sources": True,
                    "when_no_answer": "no_answer",
                    "max_chunks_to_retrieve": 5,
                    # Substring match at runtime (answer_guard) and in eval_rag.
                    "forbidden_terms": [
                        "telemóvel",
                        "telemovel",
                        "De nada",
                        "posso ajudar em mais",
                        "algo mais",
                        "estou à disposição",
                    ],
                },
                # Canal WhatsApp: resposta curta. Sem isto o projeto herda o default
                # "medium" = 2 a 4 parágrafos, que nenhum corpus consegue encurtar.
                # num_ctx: regras (~1,4k tokens) + pergunta e trechos (~0,9k) + histórico (até
                # ~0,7k) + resposta (até 1.024) passam do padrão do Ollama (4.096). Custo:
                # memória no mini62 — conferir no /usage do dashboard depois do restart.
                "llm_options": {"tone_of_voice": "direct", "message_size": "short", "num_ctx": 8192},
                # Triagem de texto que chega (e-mail) pela porta genérica /task/text_triage
                # (docs/20). As categorias são do projeto; códigos em inglês, gravados no Job.
                "tasks": {
                    "text_triage": {
                        "categories": [
                            "bike_anjo_request", "volunteering", "partnership", "press",
                            "event", "support", "other",
                        ],
                    },
                },
                # Sem isto herda o fallback genérico ("convide para contato"), que
                # empurra convite comercial quando o RAG vem fraco.
                "no_answer_fallback": (
                    "responda em no máximo uma linha, sem inventar serviço, link, "
                    "evento, prazo ou valor, e sem convidar para contato."
                ),
                "system_instruction": BIKEANJO_SYSTEM_INSTRUCTION,
                "router": {"extra_system_block": BIKEANJO_ROUTER_BLOCK},
                # 2º roteador semântico do /ask: lista fechada; o cliente executa a action.
                "ask_intent": {
                    "enabled": True,
                    "actions": [
                        {
                            "code": "event_interest_lookup",
                            "meaning": (
                                "A pessoa pergunta se já tem inscrição/interesse ou se o canal "
                                "'consegue ver' o status dela num evento."
                            ),
                        },
                        {
                            "code": "registration_completeness_lookup",
                            "meaning": "Reservado — completude de cadastro da pessoa.",
                        },
                        {
                            "code": "city_event_lookup",
                            "meaning": "Reservado — eventos na cidade da pessoa.",
                        },
                    ],
                },
                "profile_display": {
                    "labels": True,
                    # Vazio de propósito: o que a assistente deve fazer com uma jornada
                    # aberta ainda não está definido (depende do kind, do leitor e de
                    # quando é lido — decisão do Bike Anjo, não deste código).
                    # Clearance (NOIA) não entra aqui: é autorização, não contexto.
                    "glossary": {"journey_kind": {}},
                },
            })),
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
