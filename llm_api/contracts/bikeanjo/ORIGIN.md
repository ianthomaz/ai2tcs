# Origem deste pacote

Cópia de `bikeanjo2026all/docs/contracts/ai2tcs/` — os nomes de arquivo são os mesmos
dos dois lados, para `diff -r` servir de conferência.

| | |
|---|---|
| origem | `bikeanjo2026all@e78f801c` (main local pós-merge #212+#213+#214, 1/out/2026) |
| copiado em | 2026-10-01 |

**Vale o arquivo.** O serviço lê daqui, em tempo de execução, os system prompts
(`prompts/*-v1.md`) e os hints de RAG (`rag/retrieval-hints.json`); os testes
(`tests/test_bikeanjo_ops_contract.py`) validam os `*.examples.json` contra os
`*.schema.json`. Mudar o contrato é um commit em cada repositório com o mesmo
conteúdo, e este arquivo ganha o SHA novo.

Implementação: `app/bikeanjo/` · documentação: `docs/18-bikeanjo-ops-ports.md`.
