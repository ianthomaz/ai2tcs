# 22 — Julgamentos de resposta: o projeto ensina o serviço (`/ratings`)

Pessoas de um projeto julgam respostas do serviço (no Bike Anjo, o painel `/adm/shadow-llm`).
Esta porta recebe esses julgamentos e transforma em duas coisas, as duas **só com uma pessoa
no meio**:

1. **Proposta de termo proibido** a partir de resposta reprovada. Fica pendente até alguém
   aprovar; aprovada, entra em `config_json.policies.forbidden_terms` do projeto, a mesma lista
   que a trava (`app/rag/answer_guard.py`) já lê.
2. **Exemplo aprovado** a partir de resposta «ótima» (`great`). Entra no prompt do `/ask` só
   quando o projeto liga `policies.rated_examples`.

| | |
|---|---|
| Código | `llm_api/app/ratings/` — `logic.py` (regras puras), `store.py` (banco), `routes.py` |
| Tabelas | `answer_ratings`, `rating_proposals` (migration `20261110120000_answer_ratings`) |
| Testes | `tests/test_answer_ratings.py` |

Projeto: o da chave; com o token do operador, `project_id` no corpo (ou na query do `GET`).

---

## 1. `POST /ratings`

```json
{ "items": [ {
    "source_ref": "zap:log:4821",
    "rating": "bad",
    "question": "Tem oficina em Belém amanhã?",
    "answer": "Tem sim, inscreva-se em https://bikeanjo.org/belem",
    "reason": "inventou link",
    "signals": { "unsupported_links": ["https://bikeanjo.org/belem"] },
    "suggested_terms": ["garanto sua vaga"],
    "rated_at": "2026-11-10T14:03:00Z"
} ] }
```

- `source_ref`: identificador do caso no cliente (`[A-Za-z0-9:._-]`, até 120). Mandar de novo
  atualiza; `"rating": null` apaga (a pessoa desfez a nota).
- `rating`: `stop` · `bad` · `good` · `great`. `question` e `answer` obrigatórios com nota.
- `signals`: o bloco que o `/ask` devolveu ([02 § signals](./02-api-integration.md)), opcional.
- `suggested_terms`: termos que a pessoa digitou para proibir (3 a 200 caracteres), opcional.
- Até 200 itens por chamada. Resposta: `{"status": "ok", "stored", "removed", "new_proposals"}`.

**O que propõe** (só `bad` e `stop`): os links de `signals.unsupported_links` (link que o modelo
não viu); sem `signals`, todos os links da resposta quando o motivo fala de «link»; e os
`suggested_terms`. A mesma proposta vinda de vários casos acumula os `source_refs`.

## 2. `GET /ratings/proposals?status=pending`

`status`: `pending` (padrão) · `approved` · `rejected` · `all`. Cada proposta: `id`, `kind`
(`forbidden_term`), `value`, `source_refs`, `status`, `created_at`, `decided_at`, `decided_by`.

## 3. `POST /ratings/proposals/{id}/decision`

`{"decision": "approve" | "reject", "decided_by": "nome de quem decidiu"}`. Só proposta
pendente (senão 404). Aprovar `forbidden_term` grava o termo em `policies.forbidden_terms` na
mesma transação; termo repetido (sem diferença de maiúscula) não duplica.

## 4. Exemplos aprovados no `/ask`

`config_json.policies.rated_examples: N` (padrão 0, desligado). Ligado, o `/ask` busca as
respostas `great` mais recentes do projeto (até 200), escolhe as N cujas perguntas mais
compartilham palavras de conteúdo com a pergunta nova (mínimo 25% das palavras dela) e põe no
fim do system prompt, com a instrução de seguir tom e tamanho e só usar fato, data ou link que
os trechos confirmem. Antes de ligar: `scripts/eval_gate.py` do projeto.

## 5. Dado guardado

`answer_ratings` guarda pergunta e resposta de propósito (são o exemplo). A retenção de texto
dos jobs (`policies.text_retention_days`) não apaga julgamentos; o cliente apaga um caso
mandando `"rating": null`.

---

**Anterior:** [21-review-nov2026.md](./21-review-nov2026.md)
