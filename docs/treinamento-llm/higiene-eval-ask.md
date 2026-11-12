# Higiene do eval `/ask` (bikeanjoall_2026 e o mesmo molde)

Absorve a nota de passagem `RAG_melhorias_tmp.md` (11/nov/2026). Objetivo: o portão
não dizer «RAG morto» quando o problema é **métrica misturada** ou corpus sujo.

## Snapshot que motivou a nota

`eval_gate` `bikeanjoall_2026` ~ **45/130** · ops BA ~ **40/45** · RAG `/ask` ~ **5/85**.
Serviço e observe ok; o número feio do `/ask` junta:

1. casos de sombra WhatsApp avaliados com keywords de prosa;
2. ruído/contradição no corpus (lado BA limpa em `bibliotecaConteudoLLM/` + hints).

Ops sem RAG (`feedbackTriage`, `healthNormalize`) **não** entram neste fio.

## Buckets (separar no harness)

| Bucket | Critério de sucesso | Onde testar | Exemplo |
|---|---|---|---|
| **A · org factual** | keywords / fatos; prosa `org_general` | score RAG clássico | «o que é a Bike Anjo?» |
| **B · USER×sistema** | `knowledge_kind=user_system` + `action`; **answer vazio** | eval de intent | «já me inscrevi?» |
| **C · ruído** | `no_answer` / `unknown` / status | status, não texto | emoji · «obrigado» |
| **D · org com link** | `org_general`, **proibir** lookup de inscrição | intent + keywords | «link do cadastro» |

Casos oficiais BA: `llm_api/contracts/bikeanjo/ask-intent.eval.json` (20 casos).
Fonte `eval_questions.json`: classificar os ~85 em A–D antes de cravar baseline.

**Baseline útil** = só bucket **A** depois de re-ingest do corpus limpo.

## O que «bom» significa (Bike Anjo)

1. Institucional / EBA → prosa curta no corpus; sem inventar URL/`magic=`.
2. Status de inscrição → `intent` + lookup no Zap; sem prosa inventando inscrição.
3. Ruído → silêncio (`no_answer`).
4. Live → só com gate do Zap; shadow julga sempre.

Professor / segunda opinião (janela + estado do caso):
[segunda-opiniao-agente.md](./segunda-opiniao-agente.md).

## Flags (ligar uma de cada vez · chave scoped do projeto)

Depois de espelhar contratos BA → `llm_api/contracts/bikeanjo/` e re-ingerir:

1. Classificar eval em A–D; portão de intent com os 20 casos BA.
2. Rodar só A → baseline «RAG real».
3. `policies.retrieval_query_with_history`
4. `policies.embedding_query_instruction`
5. híbrido / rerank (custar CPU no mini62)
6. `policies.rated_examples` só com `/ratings` `great` estável ([22](../22-answer-ratings.md))

## Não fazer neste fio

- Trocar modelo / temperatura «para ver»
- Indexer Python fora da API viva (`:28471` / embed do serviço)
- Ligar envio live do Zap «porque o RAG melhorou»
- Misturar melhoria de saúde/triagem neste pacote
- Ingerir feedback, saúde ou chamado no Chroma

## Mapa rápido

| Achado | Onde mexer |
|---|---|
| Eval mistura sombra com factual | `eval_questions.json` / harness por bucket · `ask-intent.eval.json` |
| Retrieve sobe doc errado | `retrieval-hints.json` (contrato BA) · seed |
| Intent errado | seed `ask_intent` · frases no Zap |
| Ratings / professor | [22](../22-answer-ratings.md) · [segunda-opiniao-agente.md](./segunda-opiniao-agente.md) |
