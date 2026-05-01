# ai2tcs

Repositório do **produto LLM/API** (automação e integrações): API FastAPI com RAG multi-projeto, NF Extract, dashboard, jobs e documentação de contratos.

| Área | Onde |
|------|------|
| API e serviços | [`featureLLM/`](featureLLM/) — ver [`featureLLM/README.md`](featureLLM/README.md) |
| Extração fiscal (serviço auxiliar) | [`ExtratNFdata/`](ExtratNFdata/) |
| Manual da API NF Extract (rotas, payloads) | [`docs/ManualNF_Extract`](docs/ManualNF_Extract) (na raiz do clone **ai2tcs**) |
| Deploy local (Docker) | `./scripts/deploy_llm.sh` |
| Smoke NF Extract | `./scripts/nf_extract_smoke.py` |

## Operações e infra ITCS

Documentação confidencial (máquinas, Cloudflare, credenciais, fluxos de empresa) foi **deslocada** para o workspace local **`/Users/ianthomaz/Documents/ITCS`** (snapshot em `mirror-from-ai2tcs/2026-04-30/` com `MANIFEST.md`). Backup adicional: repositório **itcsAdm** no GitHub.

Credenciais locais (`_credentials/`, `.basicITCS_getAware`) continuam à raiz deste clone se as mantiveres; não são commitadas (ver `.gitignore`).

## Convenções

- **Código e comentários técnicos:** inglês.
- **Interface e mensagens ao utilizador:** português (público BR).
- **Estado em listas em `.md`:** `[ x ]` resolvido, `[ ]` pendente (sem emojis nos `.md`).
