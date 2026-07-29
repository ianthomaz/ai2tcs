# 15 — Correções em projetos satélite (handoff)

Ações **fora do repo ai2tcs** que completam o plano de melhorias. Implementação da API fica em `llm_api/`; cada projeto cliente aplica a parte dele.

**Anterior:** [14-ian-zap-personal.md](./14-ian-zap-personal.md) · **Seguinte:** [01-overview.md](./01-overview.md)

---

## 033_aiClaudia (`/Users/ianthomaz/Documents/projects/033_aiClaudia`)

| Item | Ação | Onde |
|------|------|------|
| Seed API | Rodar `python3 llm_api/scripts/seed_aiclaudia.py` e `POST /ingest` com `project_id=aiclaudia` | ai2tcs |
| Personas DB | Chamar `load_rndbase.py` no startup | `033_aiClaudia/deploy/` — wired in `start_aiclaudia.sh` |
| API key | Usar `itcs_aiclaudia_*` em vez de token global | env do deploy |
| Histórico | Enviar **só** `history` **ou** contexto no `system_prompt`, não os dois | `simple_prompt_selector.py` — fixed |
| Dedup | Já desligado via seed (`dedup_ttl_seconds: 0`) | ai2tcs DB |

Checklist pós-deploy:

1. [ x ] Confirmar `prompt_profile: creative` e `rag_mode: disabled` no dashboard (seed ai2tcs).
2. [ x ] Pergunta off-topic não deve mencionar Mobi — guard + prompt creative na API (`answer_guard.py`, eval `forbidden_keywords`).
3. [ x ] `SELECT COUNT(*) FROM rndbase` = 25 no Postgres do aiClaudia (validado 2026-06-27 via `load_rndbase` no startup).

---

## estudosMobi (`/Users/ianthomaz/Documents/projects/estudosMobi`)

| Item | Ação |
|------|------|
| Seed | `python3 llm_api/scripts/seed_estudosmobi.py` |
| `project_id` | Alinhar env para um slug único (`estudosmobi`) |
| Sources | Ordem: `fluxosLLM/` primeiro, depois `bibliotecaConteudoLLM/` |
| API key | Chave escopada ao projeto, não token global |
| Re-ingest | Após editar `instrucoes-llm.md` ou biblioteca |

Opcional no host da API:

```bash
ESTUDOSMOBI_SOURCES=/path/estudosMobi/fluxosLLM,/path/estudosMobi/bibliotecaConteudoLLM
```

---

## zapzap / BikeAnjo / outros clientes HTTP

| Item | Ação |
|------|------|
| Auth | `itcs_{project_id}_*` por bot |
| Router | `config_json.router.extra_system_block` para regras extras (padrão `ian_zap`) |
| Boleto | `POST /boletoExtract` + step `payment_boleto_confirmation` em `/extract` |
| Webhook | `callback_url` em `POST /ask` (HTTPS) em vez de polling longo |

---

## Novo projeto (self-service mínimo)

```bash
cd llm_api
python3 scripts/create_project.py meu_projeto_2026 --name "Meu Projeto"
python3 scripts/create_project.py meu_projeto_2026 --profile sales  # opcional
# POST /ingest + usar SDK:
# from sdk.client import LLMClient
```

Ver também [02-api-integration.md](./02-api-integration.md) e template em `llm_api/project_library/_template/`.

---

## Flags RAG (ai2tcs `.env`)

| Variável | Default | Efeito |
|----------|---------|--------|
| `RAG_RERANK_ENABLED` | false | Cross-encoder após Chroma (override por projecto em `policies.rag_rerank_enabled`) |
| `RAG_HYBRID_ENABLED` | false | Boost por keyword overlap (override por projecto) |
| `RAG_REFLECTION_ENABLED` | false | Self-check pós-resposta |
| `EMBEDDING_CACHE_ENABLED` | true | LRU de embeddings de pergunta |

Eval manual: `python3 scripts/eval_rag.py --project aiclaudia` (inclui off-topic + `forbidden_keywords: mobi, mobicontabil`).
