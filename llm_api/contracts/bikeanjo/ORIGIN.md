# Origem deste pacote

Cópia de `bikeanjo2026all/docs/contracts/ai2tcs/` — os nomes de arquivo são os mesmos
dos dois lados, para `diff -r` servir de conferência.

| | |
|---|---|
| origem | `bikeanjo2026all@e902f967a2178c873914475d63ab7a165d8a1e79` |
| copiado em | 2026-09-28 |

**Vale o arquivo.** O serviço lê daqui, em tempo de execução, os system prompts
(`prompts/*-v1.md`) e os hints de RAG (`rag/retrieval-hints.json`); os testes
(`tests/test_bikeanjo_ops_contract.py`) validam os `*.examples.json` contra os
`*.schema.json`. Mudar o contrato é um commit em cada repositório com o mesmo
conteúdo, e este arquivo ganha o SHA novo.

Implementação: `app/bikeanjo/` · documentação: `docs/18-bikeanjo-ops-ports.md`.
