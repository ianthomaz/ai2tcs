# Documentação — LLM API

Índice em camadas. Tudo em português.

**Repositório:** **ai2tcs** — esta pasta é `featureLLM/docs/` no clone. Manual **só** de NF Extract: [`../../docs/ManualNF_Extract`](../../docs/ManualNF_Extract). Detalhes sensíveis da tua rede: pasta local **`local-only/`** (ver [`../../docs/LOCAL_ONLY.md`](../../docs/LOCAL_ONLY.md)). Infra interna da empresa não entra neste repo.

---

## Integração (contrato HTTP)

Quem **consome** a API deve usar sobretudo:

| Documento | Uso |
|-----------|-----|
| [**MANUAL_INTEGRACAO.md**](./MANUAL_INTEGRACAO.md) | URL base, auth, endpoints, exemplos Python/Node/Bash, troubleshooting |
| [**MANUAL_REINTEGRACAO.md**](./MANUAL_REINTEGRACAO.md) | Migração: chaves por projeto, fleet de modelos, `/router`, ingest upload, checklist pré-deploy |

---

## LLM, modelos e ambiente

| Documento | Uso |
|-----------|-----|
| [CALIBRACAO_LLM.md](./CALIBRACAO_LLM.md) | Desvios da LLM, mitigações, boas práticas de tom |
| [PROJECT_CONFIG_EXAMPLES.md](./PROJECT_CONFIG_EXAMPLES.md) | Chunking, temperatura, políticas por projeto |
| [UPGRADE_MODELO_LLM.md](./UPGRADE_MODELO_LLM.md) | Trocar modelo Ollama / variáveis relacionadas |
| [`.env.example`](../.env.example) | Nomes e exemplos de variáveis (sem segredos) |

---

## Features (contratos estreitos)

| Documento | Uso |
|-----------|-----|
| [EDU_API_CONTRACT.md](./EDU_API_CONTRACT.md) | `/edu/*` — chat tutor, exercícios, vocabulário, progresso |
| [NABIL_QUALIFY_CAPTION_API.md](./NABIL_QUALIFY_CAPTION_API.md) | `POST /nabilvideomap/qualify-caption` |

---

## Operação de rede

| Documento | Uso |
|-----------|-----|
| [OPERACAO_TAILSCALE.md](./OPERACAO_TAILSCALE.md) | Tailscale, Serve, fallbacks (túnel, proxy) |

---

## Desenvolvimento e roadmap

| Documento | Uso |
|-----------|-----|
| [DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md) | Setup dev, arquitetura, testes, extensão da API |
| [UPGRADES.md](../UPGRADES.md) | Roadmap e melhorias planeadas |

---

## Plano histórico (referência)

| Documento | Uso |
|-----------|-----|
| [PLANO_CHAVES_ROTEADOR_REINTEGRACAO.md](./PLANO_CHAVES_ROTEADOR_REINTEGRACAO.md) | Plano longo: fleet, router, chaves, ingest — contexto; integração oficial continua no manual |

---

**Atalho:** usar a API → [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md). Afinar modelo e projeto → secção LLM acima. Nova feature documentada → um `.md` de contrato + linha na tabela **Features**.
