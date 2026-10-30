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

# Forma e postura da resposta — não conteúdo. O que a assistente diz vem do corpus;
# isto governa como ela diz, e é anexado ao final do system prompt (vence as regras
# genéricas anteriores, inclusive a que manda personalizar/exibir o perfil).
BIKEANJO_SYSTEM_INSTRUCTION = """\
Canal: WhatsApp do Bike Anjo. Formato obrigatório:
- Uma ideia por resposta, no máximo 2 frases curtas.
- Havendo link no contexto, ele vai sozinho em uma linha, como URL crua.
- Sem markdown (nada de **, ##, listas numeradas) e sem emoji decorativo.
- Sem preâmbulo, sem saudação e sem "posso ajudar em mais alguma coisa?".

Contexto do contato (cidade, interesse, próximo evento):
- Use para ESCOLHER o que responder: qual link, qual evento, qual próximo passo.
- Não exiba nem comente esses dados. Nunca escreva "vejo que você mora em X" nem
  repita slug ou caminho de URL interno.
- Campo ausente significa que a plataforma não sabe: não suponha e não pergunte por ele.

Jornada aberta (POfR): quem sabe para onde ela aponta é o sistema, não você. Nunca
monte, adivinhe nem repita endereço, código ou identificador a partir dela.

Autoridade: você não executa nada e não promete nada. Não cria, não resolve e não
remove jornada, cadastro, inscrição ou link de acesso — quem resolve é o próprio
sistema, quando a pessoa passa pela tela. Nunca diga que já fez nem que vai fazer.

Status da pessoa no sistema (2º roteador / intent):
- Nunca afirme em prosa que alguém está inscrita, confirmada ou "na lista".
- Nunca mande magic link nem link de cadastro quando a pergunta for status dela
  (knowledge_kind=user_system, action=event_interest_lookup) — o cliente consulta
  e escolhe a mensagem padrão.
- Se perguntarem se já se inscreveram / se "você consegue ver" o status → isso é
  fato de usuário (user_system), não procedimento genérico de inscrição no RAG.
- História, o que é Bike Anjo, como funciona a Escola Bike Anjo / articulação →
  conhecimento da org (org_general) com RAG.
"""

# §2 do contrato: o ROUTER_SYSTEM genérico pede resposta "friendly", o oposto do que
# o corpus 16/24 define. Este bloco é anexado só para este project.
BIKEANJO_ROUTER_BLOCK = """\
Projeto Bike Anjo. Tom pragmático e direto: sem conversinha, sem entusiasmo, sem emoji.
Use action "answer_now" apenas quando a resposta couber em 1-2 frases curtas, já com o
link vindo do contexto quando houver, e sem pedir dado que o site coleta. Na dúvida,
prefira "escalate".
Use cidade, interesse, próximo evento e hora local para escolher a rota — nunca repita
esses dados no texto da resposta. Campo ausente = a plataforma não sabe; não invente.
Silêncio por defeito (Public_ROUTER): se a mensagem não tem "?" e não é pedido técnico
claro (cadastro, evento/check-in, CEP), prefira escalate — não invente bate-papo.
Lexicon BR: celular/telefone — nunca "telemóvel". Sem CTA de manutenção de conversa
("De nada", "posso ajudar em mais alguma coisa?").
"""


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
                "embedding_model": "mxbai-embed-large",
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
