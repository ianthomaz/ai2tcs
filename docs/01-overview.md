# 01 — Visão geral

**Repo:** `ai2tcs`. **Código:** `llm_api/`. **Satélites:** `features/`. **Contratos e guias:** `docs/`.

**Regra de ficheiros:** manter `docs/NN-nome.md` com `NN` inteiro em **ordem crescente** (01 … 10). Ao acrescentar ou renumerar capítulo, actualizar este índice e os links **Anterior / Seguinte** nos próprios ficheiros.

**Fora da sequência numérica:** `docs/refs/` (rede Tailscale, nginx, `ManualNF_Extract`).

---

## Integração: escopo, itcs-webplace e customização

Este repositório foi pensado para mostrar **estrutura**, **contratos HTTP** e **padrões** — para um novo produto **saber como se adaptar** (auth, `project_id`, ingest, jobs, exemplos de payloads), **não** para entregar um manual fechado ao **100%** para cada tipo de projecto que possa existir. Os exemplos concretos (bibliotecas, rotas como `/nabilvideomap/qualify-caption`, zapzap, NF, etc.) ilustram **encaixes reais**, não um catálogo exaustivo de domínios.

A API LLM documentada aqui vive no ecossistema **itcs-webplace** (operada nesse contexto). Quem integrar de fora deve seguir os mesmos contratos públicos e tratar `project_id`, biblioteca e `config_json` como o **seu** espaço dentro da mesma instância.

Se o teu projecto **precisa de padrões específicos** (prompts, campos extra, nova rota, formato de job, língua, limites), **é possível alinhar todo o fluxo** com quem mantém a API: na prática, quando o projecto **sabe pedir** — lista de **rotas** e **requests/responses** desejados, exemplos de legenda ou mensagem, restrições — pode-se devolver um desenho coerente (incluindo prompts ou notas que referenciem esses endpoints) em coordenação com a manutenção, sem obrigar esse detalhe a viver só em `local-only` para sempre.

---

## Índice

| Assunto | Ficheiro |
|---------|----------|
| API HTTP (auth, URLs, exemplos, onboarding chave § 1.3) | [02-api-integration.md](./02-api-integration.md) |
| Migração: chaves por projeto, fleet, `/router` | [03-api-reintegration.md](./03-api-reintegration.md) |
| Código: setup, testes, estrutura | [04-developer-guide.md](./04-developer-guide.md) |
| Componentes (API, worker, dados, rede) | [05-architecture.md](./05-architecture.md) |
| Contrato `/edu/*` | [06-edu-contract.md](./06-edu-contract.md) |
| Calibração LLM, desvios, mitigação | [07-llm-calibration.md](./07-llm-calibration.md) |
| `config_json`, chunking, políticas por projeto | [08-project-config.md](./08-project-config.md) |
| Ollama: modelos, variáveis `OLLAMA_*` | [09-model-upgrade.md](./09-model-upgrade.md) |
| Contexto histórico (router, fleet, ingest) | [10-historical-router-plan.md](./10-historical-router-plan.md) |
| Roadmap de melhorias (LLM / RAG / produto) | [11-improvements-roadmap.md](./11-improvements-roadmap.md) |
| Operações LLM / RAG (checklist enxuto) | [12-llm-fleet-rag-operations.md](./12-llm-fleet-rag-operations.md) |
| Ian Zap pessoal (`ian_zap`, rota `cursor`) | [14-ian-zap-personal.md](./14-ian-zap-personal.md) |
| Handoff: correções em projetos satélite | [15-cross-project-fixes.md](./15-cross-project-fixes.md) |

**NF Extract:** [refs/ManualNF_Extract](./refs/ManualNF_Extract). **Variáveis (sem segredos):** [`llm_api/.env.example`](../llm_api/.env.example). **Roadmap código:** [`llm_api/UPGRADES.md`](../llm_api/UPGRADES.md).

**Dashboard Google:** no repositório público **não** há e-mails em código; define `DASHBOARD_GOOGLE_*`, `DASHBOARD_OAUTH_REDIRECT_BASE` e **`DASHBOARD_ALLOWED_EMAILS`** no `llm_api/.env` (ou env do container). A allowlist é **obrigatória** para o login Google funcionar (minúsculas; vazio bloqueia todos). Ver `llm_api/.env.example` e [refs/cloudflare-edge.md](./refs/cloudflare-edge.md).

---

## `docs/refs/`

Índice: [refs/README.md](./refs/README.md).

| Conteúdo | Ficheiro |
|----------|----------|
| Tailscale, Serve, túnel, proxy | [refs/operacao-tailscale.md](./refs/operacao-tailscale.md) |
| Cloudflare (`llm.webplace.cc`, TLS / OAuth / WAF) | [refs/cloudflare-edge.md](./refs/cloudflare-edge.md) |
| Exemplo nginx (tailnet) | [refs/nginx/itcsVM2.conf](./refs/nginx/itcsVM2.conf) |

---

## `local-only/`

Directório na **raiz do clone**, no [`.gitignore`](../.gitignore).

- `local-only/docs/` — notas por projeto; ver `README.md` dentro dessa pasta.
- Mapa de rede (IPs Tailscale, hostnames, URLs).
- Variáveis e snippets sensíveis.

Em `docs/`: placeholders (`<tailnet-host>`, etc.) e contratos HTTP. **llm_server:** máquina onde corre a API nas secções de rede.

---

**Autoria:** ITCS-Webplace — CNPJ 65.998.990/0001-44 — [email@webplace.cc](mailto:email@webplace.cc).

**Anterior:** — · **Seguinte:** [02-api-integration.md](./02-api-integration.md)
