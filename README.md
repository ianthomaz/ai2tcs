# ai2tcs

Hub ITCS: manifest `itcsManifest.yaml` — contrato em 0MM_ITCS `docs/06_project_hub_contract.md`


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
| QA ao vivo (rotas + uma pergunta curta) | `cd llm_api && python3 tests/test_live_smoke.py` — ver [`docs/12-llm-fleet-rag-operations.md`](docs/12-llm-fleet-rag-operations.md) |
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

## Princípio: serviço de vários projetos

O ai2tcs serve vários projetos. O Bike Anjo é o primeiro cliente e traz as demandas, mas o
que se constrói aqui é **para qualquer projeto**:

- Capacidade nova nasce **genérica**: tarefa em arquivo (`llm_api/tasks/`, [docs/20](docs/20-text-tasks.md)),
  vocabulário e limites na configuração do projeto (`config_json`), chave do próprio projeto.
- Código com nome de projeto (`app/bikeanjo/`) só para o que é regra daquele projeto e não
  cabe em configuração — e mesmo assim entra pela porta comum (`/task/{task_id}`), com a
  lista de projetos que podem usar declarada na própria tarefa.
- Antes de escrever código para um projeto, perguntar: outro projeto usaria isto trocando só
  a configuração? Se sim, é tarefa genérica.

## Convenções

- **Código e comentários técnicos:** inglês.
- **Interface e mensagens ao utilizador:** português (público BR).
- **Estado em listas em `.md`:** `[ x ]` resolvido, `[ ]` pendente (sem emojis nos `.md`).

## Contribuir, segurança e licença

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — PRs, convenções, testes.
- **[SECURITY.md](SECURITY.md)** — reporte responsável de vulnerabilidades.
- **[LICENSE](LICENSE)** — MIT; titular dos direitos: **ITCS-Webplace** (CNPJ 65.998.990/0001-44). Para outra licença comercial, abre discussão antes de fork “fechado”.
