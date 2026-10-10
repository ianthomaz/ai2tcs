# Origem deste pacote

Cópia de `bikeanjo2026all/docs/contracts/ai2tcs/` — os nomes de arquivo são os mesmos
dos dois lados, para `diff -r` servir de conferência.

| | |
|---|---|
| origem | `bikeanjo2026all@b01266a5` (branch `claude/bike-anjo-llm-integration-7fsuhp`, PR #228) |
| copiado em | 2026-10-10 |
| fora da cópia | `runs/` (logs de lote com texto de saúde; este repositório é público) |

**Vale o arquivo.** O serviço lê daqui, em tempo de execução, os system prompts
(`prompts/feedback-triage-v2.md`, `health-normalize-v1.md` + few-shots, `reply-suggest-v1.md`) e os hints de RAG (`rag/retrieval-hints.json`); os testes
(`tests/test_bikeanjo_ops_contract.py`) validam os `*.examples.json` contra os
`*.schema.json`. Mudar o contrato é um commit em cada repositório com o mesmo
conteúdo, e este arquivo ganha o SHA novo.

Implementação: `app/bikeanjo/` · documentação: `docs/18-bikeanjo-ops-ports.md`.
