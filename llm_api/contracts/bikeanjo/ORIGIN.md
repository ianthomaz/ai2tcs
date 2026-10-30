# Origin

Synced from BikeAnjo_Sistema2026 main `8655e614` (AC1 handoff, 2026-10-29).

## Intent v1 (2º roteador semântico do `/ask`) · 2026-10-30

ai2tcs passa a devolver `result.intent` quando o projeto tem `config_json.ask_intent.enabled`:

- `knowledge_kind`: `org_general` | `user_system` | `unknown`
- `action`: código da lista fechada do projeto (ou null)
- `action_payload`: objeto opcional

Bike Anjo (`bikeanjoall_2026`): action viva `event_interest_lookup`; reservadas
`registration_completeness_lookup`, `city_event_lookup`. Em `user_system` o serviço
não faz RAG e deixa `answer` vazio — o cliente consulta o banco e escolhe a mensagem.

Contrato: `ask.schema.json` / `ask.examples.json`. Eval offline:
`llm_api/tests/eval/ask_intent_cases.json`.
