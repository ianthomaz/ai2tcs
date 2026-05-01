# ai2tcs

Repositório **público** do produto **LLM/API**: FastAPI com RAG multi-projeto, extração fiscal auxiliar (NF), dashboard, filas de jobs e documentação de **contratos HTTP** para integradores e para ferramentas (ex. IAs) lerem o desenho do sistema.

| Área | Onde |
|------|------|
| Índice da documentação da API | [`featureLLM/docs/INDEX.md`](featureLLM/docs/INDEX.md) |
| API e serviços | [`featureLLM/`](featureLLM/) — [`featureLLM/README.md`](featureLLM/README.md) |
| Extração fiscal (serviço auxiliar) | [`ExtratNFdata/`](ExtratNFdata/) |
| Manual NF Extract (rotas, payloads) | [`docs/ManualNF_Extract`](docs/ManualNF_Extract) |
| Notas **não** versionadas (IPs, hosts reais) | Criar [`local-only/`](docs/LOCAL_ONLY.md) — ver [`docs/LOCAL_ONLY.md`](docs/LOCAL_ONLY.md) |
| Deploy local (Docker) | `./scripts/deploy_llm.sh` |
| Smoke NF Extract | `./scripts/nf_extract_smoke.py` |

## Operações internas (fora deste repo)

Documentação confidencial de infra da organização (máquinas, DNS, credenciais) fica noutros repositórios ou no teu workspace privado — não neste clone público.

Credenciais locais (`_credentials/`, `.basicITCS_getAware`) podem existir à raiz do teu clone; **não** são commitadas (ver `.gitignore`).

## Convenções

- **Código e comentários técnicos:** inglês.
- **Interface e mensagens ao utilizador:** português (público BR).
- **Estado em listas em `.md`:** `[ x ]` resolvido, `[ ]` pendente (sem emojis nos `.md`).
