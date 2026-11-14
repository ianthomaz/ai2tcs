# Antigravity no mini62: a ponte do Docker até o professor

A Antigravity é o professor pago da segunda opinião (dono, 13/nov/2026). A API do ai2tcs
roda no Docker; a Antigravity roda no macOS, na sessão do usuário logado. Este documento é
a ponte entre os dois. Porta e regras da fila: [26](../26-second-opinion.md).

**Build verificado:** Antigravity 2.31.2 no mini62. Não existe binário `agy` / `agy run` no PATH.
O professor entra pelo runner `llm_api/scripts/antigravity_agent_runner.py` (HTTP local ao
`language_server` + leitura do transcript JSONL).

## 1. O caminho de um caso

```text
Zap / projeto ──POST /second-opinion──▶ API (Docker) ──grava──▶ second_opinions
                                          │
                                          └─POST host.docker.internal:9191/notify (campainha)
                                                        │
worker no Mac (second_opinion_worker.py --listen) ◀─────┘
  1. pega o caso       POST /second-opinion/worker/claim     (token do worker)
  2. consulta o caso   GET  PROD_READONLY_URL (chave 2)      (só leitura, sem dado pessoal)
  3. chama o professor antigravity_agent_runner.py {prompt_file}
       → POST SendAgentMessage no language_server (caso no body HTTP, nunca no argv/ps)
       → poll brain/<id>/.../transcript_full.jsonl até PLANNER_RESPONSE DONE
  4. devolve           POST /second-opinion/worker/{id}/result
  └─ volta a esperar parado (0% de CPU)
```

O prompt que a Antigravity recebe já traz tudo: as regras do professor
(`teacher_prompt.md`), as regras da casa e as diretrizes do projeto
(`llm_api/project_library/`, [27](../27-projetos-e-aprendizado.md)), as notas do projeto, o
caso e os fatos consultados agora. Ela não precisa abrir pasta do ai2tcs.

## 2. O manual antigo vs o que vale agora

| Ideia antiga / proposta | Como fica | Por quê |
|---|---|---|
| Campainha em `:9191` acorda `--once` | o próprio worker escuta (`--listen`) e esvazia a fila | um processo só |
| Devolver em `localhost:8000/second-opinion/result` | `POST {API}/second-opinion/worker/{id}/result`, API em `127.0.0.1:28471` | token do worker; sem ele, 404 |
| Credenciais em `local-only/credentials/{projeto}.env` | igual | fora do Git |
| `agy run` / `agy --mode headless` | **não existe** neste build | usar `antigravity_agent_runner.py` |
| Caso no argv / stdin do CLI | caso no **body HTTP** `SendAgentMessage` | fora do `ps` |
| Poll no SQLite `conversations/<id>.db` | poll em `brain/<id>/.system_generated/logs/transcript_full.jsonl` | texto JSONL (`PLANNER_RESPONSE`), sem protobuf |
| Uma conversa nova por caso | uma conversa de professor reutilizada (`second_opinion_teacher_state.json`, até 40 turnos) | menos lixo no hub |
| Diretrizes no disco do agente | vão no prompt, de `project_library/` | o runner não aponta workspace no repo ai2tcs |
| Consulta produção pelo agente | quem faz é o **worker** (chave 2); fatos entram no prompt | agente sem chave de projeto |
| Porta `…/case-check?userId=…` | `GET /api/llm/view?view=case&source_ref=…&subject_ref=…` | visão LLM do Bike Anjo |
| Saída: só o JSON | runner imprime JSON no stdout; API valida com `normalize_opinion` | campo inválido → `failed` |

## 3. Arquivos no mini62 (fora do Git)

`local-only/second_opinion_worker.env`:

```bash
SECOND_OPINION_WORKER_TOKEN=…            # o mesmo do .env da API
SECOND_OPINION_AGENT_CMD=python3 /Users/ianthomaz/Documents/projects/ai2tcs/llm_api/scripts/antigravity_agent_runner.py {prompt_file}
SECOND_OPINION_AGENT_NAME=antigravity
SECOND_OPINION_TIMEOUT_S=180
```

O runner descobre sozinho `ANTIGRAVITY_LS_ADDRESS` e `ANTIGRAVITY_CSRF_TOKEN` no
`language_server` da sessão, se não estiverem no env. O **Antigravity.app precisa estar
aberto** (há `language_server` escutando em `127.0.0.1`).

`local-only/credentials/bikeanjoall_2026.env`:

```bash
LLM_API_KEY=itcs_bikeanjoall_2026_…
PROD_READONLY_URL=https://sistema.bikeanjo.org/api/llm/view?view=case
PROD_READONLY_KEY=…                      # LLM_VIEW_READ_TOKEN do sistema do Bike Anjo
PROD_MUTATION_KEY=
```

API (`llm_api/.env`): `SECOND_OPINION_ENABLED=true`, o mesmo `SECOND_OPINION_WORKER_TOKEN`,
`SECOND_OPINION_NOTIFY_URL=http://host.docker.internal:9191/notify`. Projeto:
`config_json.second_opinion.enabled = true`.

## 4. Subir, um passo de cada vez

1. Antigravity.app aberto e logado na sessão do mini62.
2. `python3 scripts/second_opinion_worker.py --dry-run`: o runner devolve JSON no stdout?
3. `python3 scripts/second_opinion_worker.py --try caso.json --project bikeanjoall_2026`: um caso
   de arquivo, sem API, com a consulta de leitura e a resposta conferida como a API confere.
   Formato do arquivo: o corpo do `POST /second-opinion` ([26 § 3](../26-second-opinion.md#3-post-second-opinion-chave-do-projeto)).
4. Três casos reais do shadow pelo `--try`, comparando com o que uma pessoa responderia.
5. `launchd/com.itcs.second-opinion-worker.plist.example` em `~/Library/LaunchAgents/`
   (LaunchAgent na sessão logada; Antigravity.app precisa estar disponível nessa sessão).
6. Ligar a API e o projeto; o primeiro caso de verdade entra pelo Zap.

Pausa sem mexer em nada: `touch local-only/DISABLE_SECOND_OPINION`.

## 5. Como o runner fala com o Antigravity (fechado)

1. Lê `{prompt_file}` (o worker nunca coloca o caso na linha de comando).
2. Autodiscovery do `language_server` (porta + `--csrf_token`) se o env estiver vazio.
3. Reusa ou cria a conversa do professor (`~/.gemini/antigravity/second_opinion_teacher_state.json`).
   A criação usa `agentapi new-conversation` só com um prompt **genérico** (sem dados de caso).
4. Envia o caso com `POST …/SendAgentMessage` (body JSON).
5. Lê `~/.gemini/antigravity/brain/<id>/.system_generated/logs/transcript_full.jsonl` até um
   `PLANNER_RESPONSE` novo com `status == "DONE"` e extrai o objeto JSON do `content`.
6. Imprime esse JSON no stdout e sai.

Modelo padrão do runner: `flash_lite` (`ANTIGRAVITY_MODEL`). Timeout do poll: `ANTIGRAVITY_TIMEOUT`
(default 160 s); o worker usa `SECOND_OPINION_TIMEOUT_S` (default 180 s).

Fallback REST (`gemini_second_opinion_runner.py`) existe no repo, mas **não** é o professor
oficial deste plano.

## 6. Em aberto: acesso a pastas no macOS (LaunchAgent)

O ai2tcs mora em `~/Documents`, pasta que o macOS protege: processo em segundo plano que lê
ali pode disparar aviso TCC e, sem alguém para clicar, travar. Antes do launchd estável,
decidir:

- copiar/clonar o ai2tcs do worker para fora de `~/Documents` (ex.: `~/ai2tcs/`); ou
- conceder acesso a Documentos ao interpretador/`python3` que o LaunchAgent usa.

O Antigravity.app precisa estar aberto na sessão; o runner não sobe um `language_server`
standalone sozinho.
