# Expectativas de retorno — portas novas

Resumo operacional. Detalhe e regras: esquemas JSON + [10h](../../10h_ai2tcs_portas_de_texto.md).

Auth em todas: `Authorization: Bearer <token>` · JSON sync · HTTP 200 no erro de
conteúdo · `prompt_version` e `model` obrigatórios no sucesso.

---

## `POST /feedbackTriage`

**Para quê:** classificar texto de ops (feedback EBA, histórico, chamado) — tags,
urgência, scores, âncora. **Sem RAG.**

### Pedido (wire)

```json
{
  "source": "eba-feedback | historico-ciclista | support_ticket",
  "submission_id": "812",
  "subject": { "user_id": "AABC4", "dependent_id": null },
  "event_id": "C-AA002-A026",
  "locale": "pt-BR",
  "fields": { "impressao_curta": "…", "recado_livre": "… zap [contato]" },
  "scales": { "avaliacao_geral_1_5": 5 }
}
```

| Campo | Regra |
|---|---|
| `subject.user_id` | `null` em chamado sem conta |
| `fields` | só strings não vazias; já redigidas (`[contato]` / `[documento]`); histórico com prefixo `historico.` |
| `scales` | inteiros 1–5; pode ser `{}` |

### Sucesso

```json
{
  "status": "ok",
  "scores": { "text_quality": 1-5, "information_value": 1-5, "answer_solidity": 1-5 },
  "tags": ["construtiva"],
  "urgency": "none | watch | urgent",
  "anchor_quote": "≤160, quase literal de fields.*",
  "named_people": ["Ana"],
  "theme_free": null,
  "confidence": 0.86,
  "model": "…",
  "prompt_version": "triage-v1",
  "warnings": []
}
```

| Tags (allowlist) | `grave` `construtiva` `elogio_pessoa` `elogio_geral` `bug_sistema` `logistica` `aprendizado` `outro` |
| Urgência | `grave` costuma ir com `urgent`; elogio vago ≠ inventar nome |

### Erro

```json
{ "status": "error", "error": { "code": "invalid_request|timeout|model_error|unauthorized", "message": "…" } }
```

O cliente BA (`normalizeFeedbackTriageResponse`) **descarta** erro — não grava.

---

## `POST /healthNormalize`

**Para quê:** higienizar o resíduo de saúde (`outras`) que a taxonomia não mapeou.
**Não julga** gravidade, relevância nem diagnóstico. **Sem RAG.**

### Pedido

```json
{
  "source": "health",
  "person": { "kind": "user", "id": "AABC4" },
  "locale": "pt-BR",
  "known_codes": ["diabetes"],
  "free_text": "tenho asma leve e uso bombinha"
}
```

`person.id`: `user_id` L+C+C+C+N **ou** `D_…` (dependente).

### Sucesso

```json
{
  "status": "ok",
  "codes": ["asthma"],
  "outras": "usa bombinha",
  "generic_statement": false,
  "changed": true,
  "confidence": 0.9,
  "model": "…",
  "prompt_version": "health-v1",
  "warnings": []
}
```

| Campo | Expectativa |
|---|---|
| `codes` | só allowlist: `diabetes` `hypertension` `asthma` `renal` `tdah` `tea` `t21` |
| `outras` | caixa baixa, itens com `", "`, sem moldura («tenho», «sou»); `null` se tudo virou código |
| `generic_statement` | `true` **só** se o texto é «boa/ótima/tudo certo» **sem** condição/alergia/limitação/remédio — senão o texto some da coluna |

### Erro

Mesmo envelope `common` / `error`.

---

## `POST /replySuggest`

**Para quê:** sugerir resposta a chamado **em shadow** (nunca envia). **Com RAG** no
índice `bikeanjoall_2026`.

### Pedido

```json
{
  "source": "support_ticket",
  "ticket_id": "77",
  "channel": "platform | visitor | site",
  "subject": "…",
  "message": "…",
  "context": { "has_account": false, "page_url": "/contato", "city": null, "state": null }
}
```

### Sucesso

```json
{
  "status": "ok",
  "suggested_reply": "…",
  "no_answer": false,
  "confidence": 0.7,
  "sources": ["24_instrucoes_resposta"],
  "model": "…",
  "prompt_version": "reply-v1"
}
```

| Regra | |
|---|---|
| `no_answer: true` | sucesso válido; `suggested_reply` vazio |
| Não prometeu ação | «já excluí», «vou te ligar» → falha de eval |
| Grave (assédio/violência) | sempre `no_answer` — humano responde |

---

## Códigos de erro (`error.code`)

| Código | Quando |
|---|---|
| `invalid_request` | body incompleto / allowlist violada de forma irrecuperável |
| `unauthorized` | token em falta ou projeto errado (também pode ser HTTP 401/403) |
| `timeout` | modelo não respondeu a tempo |
| `model_error` | JSON inválido do modelo após retries internos |

Cliente BA mapeia para `reason: service_<code>` ou `invalid_response`.
