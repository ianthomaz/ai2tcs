# Antigravity no mini62: a ponte do Docker até o professor

A Antigravity é o professor pago da segunda opinião (dono, 13/nov/2026). A API do ai2tcs
roda no Docker; a Antigravity roda no macOS, na sessão do usuário logado. Este documento é
a ponte entre os dois e a resposta ao manual que a própria Antigravity escreveu (o que fica,
o que muda e por quê). Porta e regras da fila: [26](../26-second-opinion.md).

## 1. O caminho de um caso

```text
Zap / projeto ──POST /second-opinion──▶ API (Docker) ──grava──▶ second_opinions
                                          │
                                          └─POST host.docker.internal:9191/notify (campainha)
                                                        │
worker no Mac (second_opinion_worker.py --listen) ◀─────┘
  1. pega o caso       POST /second-opinion/worker/claim     (token do worker)
  2. consulta o caso   GET  PROD_READONLY_URL (chave 2)      (só leitura, sem dado pessoal)
  3. chama o professor agy … < prompt  (pasta temporária vazia, sem chave)
  4. devolve           POST /second-opinion/worker/{id}/result
  └─ volta a esperar parado (0% de CPU)
```

O prompt que a Antigravity recebe já traz tudo: as regras do professor
(`teacher_prompt.md`), as regras da casa e as diretrizes do projeto
(`llm_api/project_library/`, [27](../27-projetos-e-aprendizado.md)), as notas do projeto, o
caso e os fatos consultados agora. Ela não precisa abrir pasta nenhuma.

## 2. O manual da Antigravity, item a item

| Ela propôs | Como fica | Por quê |
|---|---|---|
| Campainha em `:9191` acorda `--once` | o próprio worker escuta (`--listen`) e esvazia a fila | um processo só; nada a mais para subir |
| Devolver em `localhost:8000/second-opinion/result` | `POST {API}/second-opinion/worker/{id}/result`, API em `127.0.0.1:28471` | rota com token do worker; sem ele, 404 |
| Credenciais em `local-only/credentials/{projeto}.env` | igual | fora do Git |
| Nomes `LLM_API_KEY` · `PROD_BASE_URL` · `PROD_READONLY_KEY` · `PROD_MUTATION_KEY` | `LLM_API_KEY` · **`PROD_READONLY_URL`** (a URL inteira da visão) · `PROD_READONLY_KEY` · `PROD_MUTATION_KEY` (vazia) | a URL já diz a visão (`…/api/llm/view?view=case`) |
| Ela mesma faz o `GET` com a chave de leitura | quem faz é o **worker**; ela recebe o resultado no prompt | o professor não vê chave nem tem rede: um texto da pessoa não consegue mandá-lo buscar nada |
| Ler `{Projeto}/LLM/diretrizes/` no disco | as diretrizes vão no prompt, de `project_library/{projeto}/diretrizes/` | `--workspace` na pasta do ai2tcs daria acesso a `local-only/credentials` |
| `agy --workspace …/ai2tcs` | `--workspace {workdir}` (pasta temporária vazia) | mesmo motivo |
| Caso por `stdin` | igual (comando sem `{prompt_file}`) | |
| Saída: só o JSON | igual; campo que falta vira vazio, campo fora da lista recusa o caso | `normalize_opinion` |
| Rota `…/api/internal/supervisor/case-check?userId=…&eventId=…` | `GET /api/llm/view?view=case&source_ref=…&subject_ref=…` (visão LLM do Bike Anjo) | uma porta de leitura por visões; a escrita será outra chave na mesma porta |

## 3. Arquivos no mini62 (fora do Git)

`local-only/second_opinion_worker.env`:

```bash
SECOND_OPINION_WORKER_TOKEN=…            # o mesmo do .env da API
SECOND_OPINION_AGENT_CMD=agy --mode headless --workspace {workdir} --system-prompt "Responda só com o objeto JSON pedido no texto recebido."
SECOND_OPINION_AGENT_NAME=antigravity
```

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

1. `python3 scripts/second_opinion_worker.py --dry-run`: a Antigravity responde sem tela?
2. `python3 scripts/second_opinion_worker.py --try caso.json --project bikeanjoall_2026`: um caso
   de arquivo, sem API, com a consulta de leitura e a resposta conferida como a API confere.
   Formato do arquivo: o corpo do `POST /second-opinion` ([26 § 3](../26-second-opinion.md#3-post-second-opinion-chave-do-projeto)).
3. Três casos reais do shadow pelo `--try`, comparando com o que uma pessoa responderia.
4. `launchd/com.itcs.second-opinion-worker.plist.example` em `~/Library/LaunchAgents/`
   (LaunchAgent: roda na sessão logada, onde a Antigravity está autenticada).
5. Ligar a API e o projeto; o primeiro caso de verdade entra pelo Zap.

Pausa sem mexer em nada: `touch local-only/DISABLE_SECOND_OPINION`.

## 5. O que perguntar à própria Antigravity

1. «`agy --mode headless` existe com esses nomes? Lê o texto pela entrada padrão e imprime só a
   resposta?»
2. «Em modo headless você roda comando, escreve arquivo ou acessa a rede? Como desligar os três?»
3. «`--workspace` numa pasta vazia limita o que você lê a essa pasta?»
4. «Você roda pelo launchd, sem a janela aberta, com a sessão do usuário?»
5. «Qual modelo responde um JSON curto com menos crédito, e como fixar no comando?»

## 6. Em aberto: acesso a pastas no macOS

O ai2tcs mora em `~/Documents`, pasta que o macOS protege: programa em segundo plano que lê
ali dispara o aviso de acesso e, sem ninguém para clicar, trava. O Cursor não pergunta porque
o aplicativo recebeu o acesso uma vez e o que ele abre herda. Saídas, a decidir pelo dono
antes de ligar o launchd:

- cópia do ai2tcs só para o worker fora de `~/Documents`;
- acesso a Documentos dado uma vez a um executável só do worker (mais estreito que o
  acesso total ao disco).

Nenhuma janela de terminal abre: o worker roda pelo launchd e chama a Antigravity por
processo, sem tela. Se o `agy` abrir o aplicativo, aparece no `--dry-run` feito à mão.
