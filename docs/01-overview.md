# 01 — Visão geral e mapa da documentação

Repositório **ai2tcs**: produto **LLM/API**. Código em **`llm_api/`**; satélites em **`features/`**. Esta pasta **`docs/`** é a documentação **pública** de contratos e guias; segue uma **linha numerada** (01 → …) para ler em ordem ou saltar para o capítulo certo.

**História sugerida:** visão geral (este ficheiro) → integração HTTP → reintegração/migração → desenvolvimento no repo → arquitetura → verticais (EDU, LLM, config) → anexos históricos. **Operação de rede** e **exemplos nginx** estão em **`docs/refs/`** (não são o contrato HTTP em si).

---

## Leitura por perfil

| Se queres… | Começa em |
|-------------|-----------|
| Chamar a API (auth, URLs, exemplos) | [02-api-integration.md](./02-api-integration.md) |
| Migrar chaves, fleet, `/router`, checklist | [03-api-reintegration.md](./03-api-reintegration.md) |
| Contribuir / correr testes / estrutura de código | [04-developer-guide.md](./04-developer-guide.md) |
| Visão de componentes (API, worker, dados, rede) | [05-architecture.md](./05-architecture.md) |
| Contrato `/edu/*` | [06-edu-contract.md](./06-edu-contract.md) |
| Tom da LLM, mitigações, desvios | [07-llm-calibration.md](./07-llm-calibration.md) |
| `config_json`, chunking, políticas por projeto | [08-project-config.md](./08-project-config.md) |
| Trocar modelo Ollama / variáveis | [09-model-upgrade.md](./09-model-upgrade.md) |
| Plano longo (router, chaves) — contexto histórico | [10-historical-router-plan.md](./10-historical-router-plan.md) |

**NF Extract** (`POST /nfExtract`): [refs/ManualNF_Extract](./refs/ManualNF_Extract). **Variáveis sem segredos:** [`llm_api/.env.example`](../llm_api/.env.example). **Roadmap de código:** [`llm_api/UPGRADES.md`](../llm_api/UPGRADES.md).

---

## Referências (anexos)

Índice da pasta **`refs/`:** [refs/README.md](./refs/README.md).

| Conteúdo | Onde |
|----------|------|
| Tailscale, Serve, túnel, proxy | [refs/operacao-tailscale.md](./refs/operacao-tailscale.md) |
| Exemplos nginx (nomes genéricos) | [refs/nginx/pcvelho.conf](./refs/nginx/pcvelho.conf), [refs/nginx/bikeanjovm.conf](./refs/nginx/bikeanjovm.conf) |

---

## Pasta `local-only/` (não versionada)

Cria **`local-only/`** na **raiz do clone** (ao lado de `README.md`). Está no [`.gitignore`](../.gitignore) e **não** deve ser commitada. Um `git clone` **não traz** esta pasta.

**Uso típico:**

- **`local-only/docs/`** — notas **por projeto** (ex. nabilVideoMap, chinese learning) que não entram no `docs/` público; ver `README.md` dentro dessa pasta.
- Mapa da **tua** rede: IPs Tailscale, hostnames, URLs públicas.
- Snippets sensíveis, variáveis reais, proxy.

O repositório público mantém **placeholders** (`<tailnet-host>`, etc.) e contratos em **`docs/`**. Assim o repo fica legível sem expor a topologia real.

---

**Anterior:** — · **Seguinte:** [02-api-integration.md](./02-api-integration.md)
