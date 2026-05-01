# ai2tcs

Repositório **público** do produto **LLM/API**: FastAPI com RAG multi-projeto, extração fiscal auxiliar (NF), dashboard, filas de jobs e documentação de **contratos HTTP** para integradores e para ferramentas (ex. IAs) lerem o desenho do sistema.

Motor principal em **`llm_api/`**; documentação de contratos em **`docs/`**; satélites em **`features/`**.

| Área | Onde |
|------|------|
| Índice da documentação da API | [`docs/01-overview.md`](docs/01-overview.md) |
| API LLM (FastAPI, RAG, jobs, `/nfExtract` na mesma API) | [`llm_api/`](llm_api/) — [`llm_api/README.md`](llm_api/README.md) |
| Features / serviços à parte | [`features/`](features/) — ver [`features/README.md`](features/README.md) |
| Extração fiscal (app auxiliar no monorepo) | [`features/ExtratNFdata/`](features/ExtratNFdata/) |
| Manual NF Extract (rotas, payloads) | [`docs/refs/ManualNF_Extract`](docs/refs/ManualNF_Extract) |
| Notas **não** versionadas (IPs, hosts reais) | Criar [`local-only/`](docs/01-overview.md) — ver [`docs/01-overview.md`](docs/01-overview.md) |
| Deploy local (Docker) | `./scripts/deploy_llm.sh` |
| Smoke NF Extract | `./scripts/nf_extract_smoke.py` |

## Operações internas (fora deste repo)

Documentação confidencial de infra da organização (máquinas, DNS, credenciais) fica noutros repositórios ou no teu workspace privado — não neste clone público.

**Segredos:** não colocar credenciais neste repositório. O `.gitignore` ainda ignora `_credentials/` e `.basicITCS_getAware` por compatibilidade com clones antigos; podes apagar essas pastas/ficheiros do teu disco se já não usares.

## Convenções

- **Código e comentários técnicos:** inglês.
- **Interface e mensagens ao utilizador:** português (público BR).
- **Estado em listas em `.md`:** `[ x ]` resolvido, `[ ]` pendente (sem emojis nos `.md`).
