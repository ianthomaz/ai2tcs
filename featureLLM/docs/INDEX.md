# Documentação — LLM API

Índice da documentação do projeto. Tudo em português.

**Repositório:** GitHub **ai2tcs** — esta pasta é `featureLLM/docs/` dentro do clone. Manual **só** de NF Extract: ficheiro na raiz do clone, [`../../docs/ManualNF_Extract`](../../docs/ManualNF_Extract). Infra/ops de empresa não vive neste repo (ver `README.md` na raiz do ai2tcs).

---

## Como usar a API (integração)

**Documento principal:** [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md)

Contém as informações atualizadas para quem vai **consumir** a API:

- URL base, autenticação (Bearer token)
- Endpoints: `/ask`, `/status`, `/result`, `/audio/*`, `/extract`, `/extract-multi`, `/nabilvideomap/qualify-caption`, `/router`, `/edu/*`, `/ingest`, `/projects`, `/jobs`, `/health`, `/dashboard`
- Exemplos em Python, Node e Bash
- Contexto de conversa (`user_id`), perfil de usuário
- Como incorporar um projeto (biblioteca de conteúdo, mapa de fluxos, ingest)
- Troubleshooting

Use só esse manual para integração; evita confusão com outros textos.

---

## Outros documentos

| Documento | Quando usar |
|-----------|-------------|
| [OPERACAO_TAILSCALE.md](./OPERACAO_TAILSCALE.md) | Acesso remoto à API (Tailscale, túneis, firewall) |
| [PROJECT_CONFIG_EXAMPLES.md](./PROJECT_CONFIG_EXAMPLES.md) | Configuração avançada de projetos (chunking, temperatura, políticas) |
| [CALIBRACAO_LLM.md](./CALIBRACAO_LLM.md) | **Desvios e dificuldades** da LLM (frases meta, autodesvalorização, alucinações), o que está implementado e boas práticas |
| [DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md) | Quem **desenvolve ou estende** a API (setup local, arquitetura, testes, troubleshooting de dev) |
| [EDU_API_CONTRACT.md](./EDU_API_CONTRACT.md) | Contrato **educacional**: `/edu/chat` com validação, retry, fallback estruturado fixo; `/exercise`, vocabulário, gramática, progresso |
| [NABIL_QUALIFY_CAPTION_API.md](./NABIL_QUALIFY_CAPTION_API.md) | **nabilVideoMap:** `POST /nabilvideomap/qualify-caption` — legenda → JSON síncrono (RAG opcional, retries, env de `num_predict`) |
| [UPGRADES.md](../UPGRADES.md) | Roadmap de melhorias (no diretório raiz do featureLLM) |
| [PLANO_CHAVES_ROTEADOR_REINTEGRACAO.md](./PLANO_CHAVES_ROTEADOR_REINTEGRACAO.md) | Plano: fleet de 4 LLMs (fast/compact/smart/reasoner), router triage-first com auto-selecção, paralelismo (warm-up + pool por alias), chaves por projeto no painel, ingest partilhado + upload multipart, gateway Tailscale, manual de reintegração |
| [MANUAL_REINTEGRACAO.md](./MANUAL_REINTEGRACAO.md) | **Novo (Abril 2026)**: Migração para Chaves por Projeto, Fleet de 4 LLMs, novo `/router`, ingest upload, bibliotecas partilhadas e **§6 checklist pré-deploy** |

---

**Resumo:** para usar a API → [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md). Para operar Tailscale ou configurar projetos → tabela acima. Para melhorar tom/qualidade das respostas e entender desvios da LLM → [CALIBRACAO_LLM.md](./CALIBRACAO_LLM.md). Para desenvolver a API → [DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md) e [UPGRADES.md](../UPGRADES.md).
