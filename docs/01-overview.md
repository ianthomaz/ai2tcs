# 01 — Visão geral

**Repo:** `ai2tcs`. **Código:** `llm_api/`. **Satélites:** `features/`. **Contratos e guias:** `docs/`.

**Regra de ficheiros:** manter `docs/NN-nome.md` com `NN` inteiro em **ordem crescente** (01 … 10). Ao acrescentar ou renumerar capítulo, actualizar este índice e os links **Anterior / Seguinte** nos próprios ficheiros.

**Fora da sequência numérica:** `docs/refs/` (rede Tailscale, nginx, `ManualNF_Extract`).

---

## Índice

| Assunto | Ficheiro |
|---------|----------|
| API HTTP (auth, URLs, exemplos, dashboard) | [02-api-integration.md](./02-api-integration.md) |
| Migração: chaves por projeto, fleet, `/router` | [03-api-reintegration.md](./03-api-reintegration.md) |
| Código: setup, testes, estrutura | [04-developer-guide.md](./04-developer-guide.md) |
| Componentes (API, worker, dados, rede) | [05-architecture.md](./05-architecture.md) |
| Contrato `/edu/*` | [06-edu-contract.md](./06-edu-contract.md) |
| Calibração LLM, desvios, mitigação | [07-llm-calibration.md](./07-llm-calibration.md) |
| `config_json`, chunking, políticas por projeto | [08-project-config.md](./08-project-config.md) |
| Ollama: modelos, variáveis `OLLAMA_*` | [09-model-upgrade.md](./09-model-upgrade.md) |
| Contexto histórico (router, fleet, ingest) | [10-historical-router-plan.md](./10-historical-router-plan.md) |

**NF Extract:** [refs/ManualNF_Extract](./refs/ManualNF_Extract). **Variáveis (sem segredos):** [`llm_api/.env.example`](../llm_api/.env.example). **Roadmap código:** [`llm_api/UPGRADES.md`](../llm_api/UPGRADES.md).

**Dashboard Google:** allowlist em `DASHBOARD_ALLOWED_EMAILS` (`llm_api/.env` ou env do container). Comparação com e-mail devolvido pelo Google; não usa Postgres. Defaults comentados: `llm_api/.env.example`.

---

## `docs/refs/`

Índice: [refs/README.md](./refs/README.md).

| Conteúdo | Ficheiro |
|----------|----------|
| Tailscale, Serve, túnel, proxy | [refs/operacao-tailscale.md](./refs/operacao-tailscale.md) |
| Cloudflare (`llm.webplace.cc`, TLS / OAuth / WAF) | [refs/cloudflare-edge.md](./refs/cloudflare-edge.md) |
| Exemplo nginx (tailnet) | [refs/nginx/bikeanjovm.conf](./refs/nginx/bikeanjovm.conf) |

---

## `local-only/`

Directório na **raiz do clone**, no [`.gitignore`](../.gitignore).

- `local-only/docs/` — notas por projeto; ver `README.md` dentro dessa pasta.
- Mapa de rede (IPs Tailscale, hostnames, URLs).
- Variáveis e snippets sensíveis.

Em `docs/`: placeholders (`<tailnet-host>`, etc.) e contratos HTTP. **llm_server:** máquina onde corre a API nas secções de rede.

---

**Anterior:** — · **Seguinte:** [02-api-integration.md](./02-api-integration.md)
