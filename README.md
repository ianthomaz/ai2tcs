# ai2tcs

Hub ITCS: manifest `itcsManifest.yaml` — contrato em 0MM_ITCS `docs/21_project_hub_contract.md`


Repositório **público** do produto **LLM/API**: FastAPI com RAG multi-projeto, extração fiscal auxiliar (NF), dashboard, filas de jobs e documentação de **contratos HTTP** para integradores e para ferramentas (ex. IAs) lerem o desenho do sistema.

Motor principal em **`llm_api/`**; documentação de contratos em **`docs/`**; satélites em **`features/`**.

| Área | Onde |
|------|------|
| Índice da documentação da API | [`docs/01-overview.md`](docs/01-overview.md) |
| API LLM (FastAPI, RAG, jobs, `/nfExtract` na mesma API) | [`llm_api/`](llm_api/) — [`llm_api/README.md`](llm_api/README.md) |
| Features / serviços à parte | [`features/`](features/) — ver [`features/README.md`](features/README.md) |
| Extração fiscal (app auxiliar no monorepo) | [`features/ExtratNFdata/`](features/ExtratNFdata/) |
| Manual NF Extract (rotas, payloads) | [`docs/refs/ManualNF_Extract`](docs/refs/ManualNF_Extract) |
| Rede e valores locais | Pasta `local-only/` — [`docs/01-overview.md`](docs/01-overview.md) |
| Deploy local (Docker) | `./scripts/deploy_llm.sh` |
| Smoke NF Extract | `./scripts/nf_extract_smoke.py` |

## Desenvolvimento e autoria

**ITCS-Webplace** — manutenção e desenvolvimento do produto LLM/API neste mono-repo.

| | |
|--|--|
| **Razão social** | ITCS-Webplace |
| **CNPJ** | 65.998.990/0001-44 |
| **Contacto** | [email@webplace.cc](mailto:email@webplace.cc) |

## Operações internas

Infra e credenciais da organização: repositórios privados ou `local-only/` no clone.

`.gitignore`: `_credentials/`, `.basicITCS_getAware` (legado).

## Convenções

- **Código e comentários técnicos:** inglês.
- **Interface e mensagens ao utilizador:** português (público BR).
- **Estado em listas em `.md`:** `[ x ]` resolvido, `[ ]` pendente (sem emojis nos `.md`).

## Contribuir, segurança e licença

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — PRs, convenções, testes.
- **[SECURITY.md](SECURITY.md)** — reporte responsável de vulnerabilidades.
- **[LICENSE](LICENSE)** — MIT; titular dos direitos: **ITCS-Webplace** (CNPJ 65.998.990/0001-44). Para outra licença comercial, abre discussão antes de fork “fechado”.
