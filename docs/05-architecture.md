# 05 — Arquitetura (visão do sistema)

Este capítulo resume **como as peças encaixam**. Para árvore de pastas e fluxo de desenvolvimento, o detalhe operacional está no [04-developer-guide.md](./04-developer-guide.md).

---

## Camadas

1. **Cliente HTTP** — aplicações externas ou serviços na mesma tailnet; contrato em [02-api-integration.md](./02-api-integration.md).
2. **API FastAPI** (`llm_api/app/`) — rotas síncronas e orquestração; registo de projetos; parte do trabalho pesado delega a **jobs**.
3. **Worker** (`app/jobs/worker.py`) — fila de jobs: RAG + chamadas ao modelo; conversa com **Ollama** e índices.
4. **Dados** — **PostgreSQL** (Prisma): projetos, conversas, chaves, domínio EDU, etc.; **Chroma** (ou equivalente configurado) para embeddings / retrieval conforme o desenho actual.
5. **Modelo** — **Ollama** no host (ou remoto); aliases de modelo (`fast`, `smart`, `compact`, `reasoner`) mapeados por env — ver [09-model-upgrade.md](./09-model-upgrade.md).

---

## Rede e exposição

Cenários típicos: API só em **127.0.0.1** no **llm_server**, exposição na **tailnet** (Tailscale Serve), ou **proxy/nginx** / **túnel SSH** quando a topologia não permite TCP estável. **llm_server** = papel documental da máquina onde corre a API (sem hostname real no Git). Documentação de operação: [refs/operacao-tailscale.md](./refs/operacao-tailscale.md); exemplos de config: [refs/nginx/](./refs/nginx/).

---

## Evolução e contexto longo

Roadmap e melhorias planeadas no código: [`llm_api/UPGRADES.md`](../llm_api/UPGRADES.md). Plano histórico (fleet, router, chaves, ingest — muito detalhe): [10-historical-router-plan.md](./10-historical-router-plan.md).

---

**Anterior:** [04-developer-guide.md](./04-developer-guide.md) · **Seguinte:** [06-edu-contract.md](./06-edu-contract.md)
