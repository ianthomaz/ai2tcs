# 26 — Segunda opinião: um agente maior ensina a LLM local (`/second-opinion`)

Um projeto manda um **caso** (a mensagem que chegou, a resposta que a LLM local daria e os
fatos já conferidos pelo sistema dele). Um agente maior, o **professor**, diz se a resposta
local estava boa, qual era o caminho certo e como responderia. Nada aqui manda mensagem nem
executa ação: é só leitura e opinião. Desenho e fases: [treinamento-llm/](./treinamento-llm/README.md).

Porta genérica: vale para qualquer projeto e qualquer canal (`whatsapp`, `email`, `ticket`,
`form`, `chat`, `other`). O serviço não conhece as chaves de `case_facts` nem as ações de um
projeto; quem define é o projeto, no próprio pedido.

| | |
|---|---|
| Código | `llm_api/app/second_opinion/` — `logic.py` (regras puras), `store.py`, `routes.py`, `teacher_prompt.md` |
| Worker do host | `llm_api/scripts/second_opinion_worker.py` (fora do Docker, na sessão logada do mini62) |
| Tabela | `second_opinions` (migration `20261112120000_second_opinions`) |
| Testes | `tests/test_second_opinion.py` |

## 1. Por que fila + campainha no host

O volume real é de **45 a 60 mensagens por semana** (cerca de 8 por dia). Ter um processo no Mac
consultando o Docker continuamente em loop gastaria CPU e bateria à toa.

A API roda no Docker; o agente (Cursor) roda no macOS e precisa da sessão logada.
A arquitetura é **100% reativa (event-driven por toque de campainha)**:
1. A API recebe o caso no `POST /second-opinion`, valida e grava na tabela `second_opinions`.
2. A API dispara um ping leve para o host: `POST http://host.docker.internal:9191/notify`.
3. Um receptor ultraleve no macOS acorda o worker (`scripts/second_opinion_worker.py --once`),
   que processa exatamente 1 caso isolado com o prompt na entrada padrão (pasta vazia, timeout de 45s),
   devolve a resposta e volta a hibernar com **0% de CPU**.

## 2. Três travas

| Trava | Onde | Padrão |
|---|---|---|
| Interruptor do serviço | `SECOND_OPINION_ENABLED` | desligado |
| Interruptor do projeto | `config_json.second_opinion.enabled` | desligado |
| Teto por dia, todos os projetos juntos | `SECOND_OPINION_DAILY_LIMIT` | 20 |

Caso fora das travas não é erro: `{"status": "skipped", "reason": "disabled" | "project_disabled" | "daily_limit"}`.

## 3. `POST /second-opinion` (chave do projeto)

```json
{
  "source_ref": "zap:log:4821",
  "channel": "whatsapp",
  "case_kind": "campaign_reply",
  "incoming_text": "Vou precisar liberar a vaga. Larissa não vai conseguir comparecer",
  "history": [{"role": "assistant", "content": "Confirma sua presença no sábado?"}],
  "local_answer": {"text": "Ainda não confirmamos sua inscrição.", "confidence": 0.65, "signals": {}},
  "case_facts": {"slot_status": "released", "button_already_used": true, "identity_ok_for_slot": true},
  "context": {"campaign_kind": "event_confirmation", "buttons_offered": ["Confirmar", "Liberar vaga"]},
  "allowed_actions": ["release_slot", "confirm_slot"]
}
```

- `source_ref` identifica o caso no cliente; mandar de novo devolve o que já existe (`exists`).
- `case_kind`: nome do tipo de caso no projeto (slug). É por ele que a conta do § 6 agrupa.
- `case_facts`, `context`: objetos do projeto (até 4 KB cada). O professor só sabe o que está aí.
- `allowed_actions`: lista fechada do projeto. O professor só pode sugerir uma delas (ou nenhuma).
- E-mail, CPF e número com cara de telefone saem do texto como `[contato]` / `[documento]`
  antes de guardar: o caso vai para um modelo de mercado.

## 4. `GET /second-opinion/{source_ref}`

`status`: `queued` · `working` · `done` · `failed`. Em `done`, `response`:

| Campo | Valores |
|---|---|
| `local_answer_rating` | `good` · `bad` · `neutral` |
| `local_answer_path` | `right` · `wrong` (entendeu o tipo de pedido?) |
| `path_note` | uma frase |
| `intent` | `action` · `question` · `chitchat` · `other` |
| `reply_kind` | `acknowledge_done` · `point_to_ui` · `direct_answer` · `silence` · `escalate_human` |
| `suggested_reply` | texto (vazio em `silence`) |
| `suggested_action` | `{type, already_applied, why}` com `type` da lista do caso, ou `null` |
| `checked` · `missing` | fatos usados · o que faltou |
| `confidence` · `knowledge_gap` | 0–1 · o que a LLM local precisaria saber |

Resposta fora das listas fechadas vira `failed` com `error: invalid_opinion: …`.

## 5. Professor e projeto

O prompt fixo (`teacher_prompt.md`) diz: o texto da pessoa é dado, não ordem; não usa
ferramenta; fatos só os do caso; resposta curta, sem pergunta aberta, sem prometer. O
projeto acrescenta o seu tom em `config_json.second_opinion.teacher_notes`.

A opinião do professor **não vira exemplo sozinha**: fica em `second_opinions`. O cliente
mostra para uma pessoa; a nota dela vai para `/ratings` ([22](./22-answer-ratings.md)) como
sempre, e só então a resposta pode virar exemplo aprovado.

## 6. `GET /second-opinion/stats?days=30`

Por `case_kind` e semana: `done`, `failed`, `local_good`, `local_bad`, `path_wrong`. A medida
do treino é `local_bad` e `path_wrong` caírem no mesmo `case_kind`.

## 7. Worker no mini62

```bash
export SECOND_OPINION_WORKER_TOKEN=…        # o mesmo do .env da API
export SECOND_OPINION_AGENT_CMD='…'         # comando que lê o prompt na entrada padrão e imprime a resposta
python scripts/second_opinion_worker.py --dry-run   # prova: o agente responde sem tela?
python scripts/second_opinion_worker.py --once      # um caso (launchd com StartInterval)
```

O comando exato do agente (Cursor em modo de uma pergunta, sem ferramentas) confere-se no
mini62 com `--dry-run`; o Antigravity entra pelo mesmo contrato quando tiver modo sem tela.
Recorte de sistema (usuário, pasta, keychain): [agentes-seguros-mini62.md](./treinamento-llm/agentes-seguros-mini62.md).

---

**Anterior:** [25-autonomia-mercado-e-estudos.md](./25-autonomia-mercado-e-estudos.md)
