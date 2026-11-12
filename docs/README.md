# Documentação (`docs/`)

1. Abrir [01-overview.md](./01-overview.md).
2. Ficheiros numerados `NN-*.md` nesta pasta; rede e exemplos em [`refs/`](./refs/). Operações LLM/RAG: [12-llm-fleet-rag-operations.md](./12-llm-fleet-rag-operations.md).

Contribuições ao código e contratos: [../CONTRIBUTING.md](../CONTRIBUTING.md). Licença: [../LICENSE](../LICENSE).

**Autoria / entidade:** ITCS-Webplace — CNPJ 65.998.990/0001-44 — [email@webplace.cc](mailto:email@webplace.cc).


- [13-optimization-execution-plan.md](13-optimization-execution-plan.md) — plano de execução incremental (sem quebra).
- [17-ecosystem-integration.md](17-ecosystem-integration.md) — papel do ai2tcs entre hub 0MM, zapzap e bridge Cursor.
- [17-integration-backlog.md](17-integration-backlog.md) — superfícies que esta API já oferece, o que o hub ainda não consome, backlog e perguntas em aberto.
- [18-bikeanjo-ops-ports.md](18-bikeanjo-ops-ports.md) — portas exclusivas do Bike Anjo: triagem de feedback/chamados, higienização de saúde e sugestão de resposta (shadow).
- [19-optimization-review.md](19-optimization-review.md) — revisão de otimização da LLM (out/2026): achados medidos, plano em ondas sem mudar contrato, decisões em aberto.
- [20-text-tasks.md](20-text-tasks.md) — tarefas de texto para qualquer projeto: `POST /task/{task_id}`, tarefa em arquivo, vocabulário na configuração do projeto (`text_triage`).
- [21-review-nov2026.md](21-review-nov2026.md) — avaliação, contra o código, das prioridades do Bike Anjo (S1–S4) e da revisão de arquitetura; plano em fatias F0–F4.
- [22-answer-ratings.md](22-answer-ratings.md) — julgamentos de resposta de qualquer projeto (`/ratings`): proposta de termo proibido com aprovação e exemplos aprovados no `/ask`.
- [23-ecosystem-panorama.md](23-ecosystem-panorama.md) — panorama: o ai2tcs no ecossistema ITCS, como a base é lida, o caminho para o robô conversar com mais liberdade e as frentes abertas.
- [24-ops-observe.md](24-ops-observe.md) — observação remota de operações (`GET /api/ops/observe`): stealth 404, cauda de logs limpos e visões SQL fixas com escopo por projeto.
- [25-autonomia-mercado-e-estudos.md](25-autonomia-mercado-e-estudos.md) — autonomia de LLM local, aproveitamento de 70% de RAM (M4 32GB), novos modelos de mercado (Qwen 2.5 / Gemma 3), trilha de estudos no YouTube e backlog para Bike Anjo, Chinês e Claudia.

- [treinamento-llm/](treinamento-llm/README.md) — Treinamento e inteligência LLM (segunda opinião, higiene eval, agentes seguros no mini62).
