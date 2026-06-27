# 14 — Ian Zap pessoal (`ian_zap` + Cursor bridge)

Owner WhatsApp: `+5511991051388` (`wa_id` `5511991051388`).

**Partner context (all repos):** `~/Documents/projects/zapCursorAgent/docs/09-partner-projects.md`

## Dois backends (portas diferentes)

| Modo | Porta mini62 | Contrato |
|------|----------------|----------|
| LLM | **28471** | `POST /ask`, `POST /router` com `project_id: ian_zap` + chave `itcs_ian_zap_…` |
| Cursor | **28472** | `POST /chat` em zapCursorAgent (CLI, não API Integrations) |

zapzap (itcsVM1) escolhe o modo — não partilham porta.

## Projeto LLM `ian_zap` — estado

| Item | State |
|------|--------|
| Seed (`Project` + sources → `zapCursorAgent/bibliotecaLLM_ian_zap/`) | [ x ] |
| API key (`itcs_ian_zap_…`) | [ x ] — cópia em `zapCursorAgent/ignore/ian_zap.llm_api_key` |
| Ingest básico | [ x ] — `POST /ingest` `{"project_id":"ian_zap"}` |
| zapzap `IAN_ZAP_LLM_API_TOKEN` | [ x ] — `webplacecc/zapzap/.env` |

### Bootstrap

```bash
cd ~/Documents/projects/ai2tcs
docker cp llm_api/scripts/seed_ian_zap.py llm_api-api-1:/tmp/seed_ian_zap.py
docker exec -e DATABASE_URL=postgresql://llmapi:llmapi_dev@postgres:5432/llmapi \
  -e ZAPCURSOR_REPO_ROOT=/Users/ianthomaz/Documents/projects/zapCursorAgent \
  llm_api-api-1 python3 /tmp/seed_ian_zap.py

# Key (once): llm_api/scripts/create_project_api_key.py ian_zap → guardar em zapCursorAgent/ignore/

curl -s -X POST http://127.0.0.1:28471/ingest \
  -H "Authorization: Bearer $(cat ~/Documents/projects/zapCursorAgent/ignore/ian_zap.llm_api_key)" \
  -H "Content-Type: application/json" \
  -d '{"project_id":"ian_zap"}'
```

Router: rota **`cursor`** — zapzap chama bridge `:28472`, não `/ask`.

## zapzap env

```bash
ZAP_OWNER_PHONE=5511991051388
IAN_ZAP_PROJECT_ID=ian_zap
IAN_ZAP_LLM_API_TOKEN=itcs_ian_zap_…

ZAP_CURSOR_AGENT_URL=http://100.90.214.92:28472
ZAP_CURSOR_AGENT_TOKEN=…   # = AGENT_API_TOKEN no zapCursorAgent
```

Bridge: https://github.com/ianthomaz/zapCursorAgent

**Anterior:** [12-llm-fleet-rag-operations.md](./12-llm-fleet-rag-operations.md) · **Seguinte:** [15-cross-project-fixes.md](./15-cross-project-fixes.md)
