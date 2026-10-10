# 20 — Tarefas de texto: uma porta para todos os projetos (`POST /task/{task_id}`)

Classificar, priorizar e resumir texto é o mesmo trabalho em qualquer projeto. Esta porta é o
motor único: a tarefa é **arquivo**, o vocabulário é **configuração do projeto**, e o código
não muda para um projeto novo usar.

| | |
|---|---|
| Rota | `POST /task/{task_id}` (o corpo é a entrada da tarefa) · `GET /tasks` (o que o chamador pode rodar) |
| Código | `llm_api/app/tasks/` — `engine.py` (pedido, envelope, JSON do modelo), `executor.py`, `registry.py`, `routes.py` |
| Tarefas de arquivo | `llm_api/tasks/<task_id>.json` + `llm_api/tasks/prompts/<arquivo>.md` |
| Testes | `tests/test_tasks.py` |

---

## 1. Dois tipos de tarefa, a mesma porta

| Tipo | O que é | Quem roda |
|---|---|---|
| **arquivo** | especificação JSON: esquema de entrada, esquema de saída, prompt, `prompt_version` | projeto que ligou a tarefa em `config_json.tasks.<task_id>` |
| **código** | porta com travas próprias (as do Bike Anjo, [18](./18-bikeanjo-ops-ports.md)) registrada no executor | a regra da porta: só a chave do Bike Anjo |

`feedback_triage`, `health_normalize` e `reply_suggest` respondem pela porta nova **e** pelas
rotas de sempre (`/feedbackTriage`, `/healthNormalize`, `/replySuggest`) — mesmo código, mesmo
contrato.

## 2. Acesso

| Quem chama | Projeto | Pode |
|---|---|---|
| chave de projeto | o da chave | tarefas de arquivo ligadas no projeto; tarefas de código se a regra delas aceitar |
| token do operador | `project_id` no corpo (obrigatório) | tarefas de arquivo ligadas no projeto |

Projeto que não ligou a tarefa → 403. Tarefa que não existe → 404.

## 3. Especificação de uma tarefa de arquivo

```json
{
  "task_id": "text_triage",
  "prompt_file": "text-triage-v1.md",
  "prompt_version": "text-triage-v1",
  "input_schema":  { "JSON Schema da entrada" : "…" },
  "output_schema": { "JSON Schema da saída"   : "…" },
  "project_vocabulary": { "category": "categories" },
  "input_vocabulary":   { "suggested_project": "candidate_projects" },
  "omit_from_model": [],
  "audit_fields": ["urgency", "priority", "category"]
}
```

- **`project_vocabulary`**: o campo da saída vira lista fechada com os valores de
  `config_json.tasks.<task_id>.<chave>` do projeto. Sem a lista → `invalid_request`.
- **`input_vocabulary`**: o campo da saída vira lista fechada com a lista que veio na entrada
  (ou `null`).
- As listas fechadas vão escritas no fim do system prompt e são conferidas na resposta:
  valor fora delas pede o modelo de novo, e na segunda falha sai `model_error`.
- **`omit_from_model`**: campos da entrada que não vão ao modelo (ids, por exemplo).
- **`audit_fields`**: o que a linha do `Job` guarda da resposta — só rótulos, nunca texto.

Envelope igual ao das portas do Bike Anjo: sucesso `{"status": "ok", …, "model",
"prompt_version", "warnings"}`; erro de conteúdo em HTTP 200 `{"status": "error", "error":
{"code", "message"}}`. Orçamento do modelo: `TASK_MODEL_ALIAS` (`smart`), `TASK_TIMEOUT_S`
(45), `TASK_NUM_PREDICT` (700), `TASK_TEMPERATURE` (0,1); `num_ctx` do projeto vale.

## 4. `text_triage` — a primeira tarefa de arquivo

Texto que chegou a um projeto (e-mail, formulário, chamado, chat) → `urgency` (`none` ·
`watch` · `urgent`), `priority` 1–5, `category` (da lista do projeto), `summary` (uma frase, sem
contato), `needs_reply`, `suggested_project` (só quando `candidate_projects` vem na entrada) e
`confidence`. Não responde a quem escreveu.

Ligar num projeto (dashboard → projeto → `config_json`, ou `PUT /projects/{id}`):

```json
{ "tasks": { "text_triage": { "categories": ["parceria", "suporte", "imprensa", "outro"] } } }
```

As categorias são decisão de cada projeto. Pedido:

```bash
curl -X POST "$LLM_API_URL/task/text_triage" -H "Authorization: Bearer itcs_<projeto>_…" \
  -H "Content-Type: application/json" \
  -d '{"text":"Somos uma empresa e queremos patrocinar","channel":"email"}'
```

## 5. Tarefa nova

1. `llm_api/tasks/<task_id>.json` com os esquemas e o `prompt_version`.
2. `llm_api/tasks/prompts/<arquivo>.md` — o texto abaixo da primeira linha `---` é o prompt.
3. O projeto liga em `config_json.tasks.<task_id>` (com o vocabulário, se a tarefa pedir).
4. Antes de usar de verdade: casos no `scripts/eval_gate.py` do projeto.

Mudou o prompt → `prompt_version` novo.

---

**Anterior:** [19-optimization-review.md](./19-optimization-review.md)
