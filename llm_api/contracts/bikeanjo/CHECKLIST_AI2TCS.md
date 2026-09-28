# Checklist — implementar no ai2tcs (sessão no mini62)

Pacote pronto **neste** repositório. Nada disto altera o ai2tcs sozinho: copiar e
implementar lá. Ordem pensada para uma sessão; não pular o critério de «pronto».

**Origem (Bike Anjo):** `docs/contracts/ai2tcs/` · commit a anotar ao copiar.  
**Destino sugerido:** `~/Documents/projects/ai2tcs/llm_api/contracts/bikeanjo/`.  
**API viva:** FastAPI em `llm_api/app/` · porta 28471 · auth Bearer (`LLM_API_TOKEN` ou
`itcs_<project>_<hex>`).

---

## 0. Cópia e âncora

- [x] Copiar a pasta `docs/contracts/ai2tcs/` → `llm_api/contracts/bikeanjo/`
- [x] No destino: `ORIGIN.md` com `origem: bikeanjo2026all@<SHA>` + data (o README fica igual dos dois lados)
- [x] Confirmar que **não** existiam ainda rotas `/feedbackTriage`, `/healthNormalize`,
      `/replySuggest` em `app/main.py` (estado 28/set/2026: só nf/boleto/router/ask/extract/…)

---

## 1. Base comum (uma vez)

- [x] Helper de envelope: sucesso com `status`, `confidence`, `model`, `prompt_version`,
      `warnings` (lista, default `[]`); erro HTTP 200 com
      `{"status":"error","error":{"code":"…","message":"…"}}` — códigos em
      `common.schema.json` (`invalid_request` \| `timeout` \| `model_error` \| `unauthorized`)
- [x] Token → `project_id` (mesmo mecanismo das rotas atuais); body/path de outro
      projeto → 403
- [x] Campo desconhecido no JSON: **ignorar**, nunca 400
- [x] Teste genérico: carrega `*.examples.json` e valida `request` / `response_ok` com
      jsonschema

---

## 2. `POST /feedbackTriage` (primeira porta nova)

Arquivos: `feedback-triage.schema.json` · `.examples.json` · `.eval.jsonl` ·
`prompts/feedback-triage-v1.md`.

- [x] Rota JSON sync em `app/bikeanjo/` (módulo do projeto, não `app/api/`) + `include_router` em `main.py`
- [x] Modelos de entrada/saída alinhados ao esquema (ou validação runtime)
- [x] Prompt = conteúdo de `prompts/feedback-triage-v1.md` **+**
      `prompts/feedback-triage-fewshots.md`; resposta com `"prompt_version": "triage-v1"`
- [x] Allowlist no serviço: tags, urgência, sources do esquema — valor fora da lista →
      strip / erro `invalid_request`, nunca inventar tag
- [x] **Contrato:** cada `request` em `feedback-triage.examples.json` é aceito; corpo de
      sucesso valida `response_ok`
- [ ] **Eval (pronto):** no `feedback-triage.eval.jsonl`:
  - todo caso com `tags_include` contendo `grave` → tag `grave` **e** `urgency` esperado
  - demais casos: ≥ 80% dos `expect` satisfeitos
  - `anchor_quote` ≤ 160 chars e substrato de algum `fields.*` (sem `[contato]`)
- [ ] Smoke: `curl` com Bearer do projeto `bikeanjoall_2026` + um `request` do examples

**O que o Bike Anjo faz depois (não bloqueia a rota):** CLI lote + tabela
`form_submission_triages` + digest — [10g](../../10g_feedback_triage_llm.md).

---

## 3. `POST /healthNormalize`

Arquivos: `health-normalize.*` · `prompts/health-normalize-v1.md`.

- [x] Rota JSON sync
- [x] Prompt = `prompts/health-normalize-v1.md`; `"prompt_version": "health-v1"`
- [x] Códigos só da allowlist do esquema; resto em `outras` (padrão de comparação)
- [x] **Proibido:** marcar `generic_statement: true` quando o texto escreve condição,
      alergia, limitação ou remédio — apagar o que a pessoa disse é o erro que não pode
- [x] **Contrato:** examples aceitos
- [ ] **Eval (pronto):** em `health-normalize.eval.jsonl`, **zero** violação da regra
      acima; demais ≥ 80%
- [ ] Smoke curl

**Depois no BA:** CLI + gravação com log antes/depois — [10f](../../10f_health_normalize_api_contract.md).

---

## 4. RAG — preparar índice antes de `/replySuggest` (e melhorar `/ask`)

Ver [rag/RAG_PORTAS.md](rag/RAG_PORTAS.md) · [retrieval-hints.json](rag/retrieval-hints.json) ·
[corpus-manifest.json](rag/corpus-manifest.json).

- [ ] Repo BA no mini62 no commit com `34`, `35`, stubs `06–09` reescritos e H1 `# Sobre:`
- [ ] Re-ingest: `./tools/scripts/llm-ingest-bikeanjo.sh …` ([10a](../../10a_llm_ingest_bikeanjo.md))
- [ ] Confirmar chunks de `34` e `35` no Chroma (metadata.path)
- [x] Handler `/replySuggest`: boost/downrank de `ports.replySuggest` (`app/bikeanjo/reply_suggest.py`)
- [ ] Handler `/ask`: boost/downrank + `intent_clusters` — mexe no bot em produção; fica para leva própria com eval do `/ask`

---

## 5. `POST /replySuggest` (depois das duas acima + ingest)

Arquivos: `reply-suggest.*` · `prompts/reply-suggest-v1.md` · hints em `rag/`.

- [x] Rota JSON sync **com RAG** no índice `bikeanjoall_2026` (como `/ask`)
- [x] Prompt = `prompts/reply-suggest-v1.md`; `"prompt_version": "reply-v1"`
- [x] Boost paths de suporte; downrank estatuto / `mapaFluxosLLM`
- [x] `no_answer: true` é sucesso válido (não forçar texto)
- [ ] **Eval (pronto):** nenhum caso promete ação já feita («já excluí», «vou te enviar»)
      nem inventa URL; caso grave (assédio/violência) → sempre `no_answer`
- [x] Contrato examples aceitos

**Depois no BA:** tabela `support_ticket_suggestions` + UI shadow — [10h §5.2](../../10h_ai2tcs_portas_de_texto.md).

<!-- [needsReview] r07 do reply-suggest.eval.jsonl proíbe qualquer "https://", mas o
     prompt reply-v1 e a trava do ai2tcs aceitam os domínios canônicos (bikeanjo.org,
     cadastro., sistema.). Rascunho que cite https://bikeanjo.org reprova no eval e passa
     na regra. Dono decide qual vale. -->

---

## Pôr no ar (mini62) — só com ordem do dono

Os itens «Eval (pronto)» e «Smoke» acima medem o modelo vivo, então esperam o deploy.

1. `git pull` do ai2tcs + rebuild (`./scripts/deploy_llm.sh`).
2. Smoke: `curl` com a chave `bikeanjoall_2026` num `request` dos examples → `status: ok`;
   com chave de outro projeto → 403.
3. Eval: `LLM_API_TOKEN=<chave bikeanjoall_2026> python llm_api/scripts/eval_bikeanjo_ops.py`
   — imprime caso a caso e dá **PRONTO** / **não pronto** por porta com os critérios acima.
4. Só com **PRONTO**: lote de ensaio no sistemaBA (`--dry-run --limit=30`) — com ok explícito.

---

## 6. Não fazer nesta leva (evitar escopo)

- Migrar NF/boleto para `error: {code,message}` (só documentado; aditivo depois)
- Ingerir feedback/saúde no índice vetorial (dado pessoal **fora** do RAG)
- Ligar cron/CLI do sistemaBA sem ok explícito do dono (API externa paga/cota)

---

## Verificação cruzada rápida

| Pergunta | Onde olhar |
|---|---|
| O que o BA manda no wire? | `*.examples.json` → `request` |
| O que o BA aceita de volta? | `normalize*` em `feedback-triage-shared.ts` / `health-normalize-shared.ts` |
| Vocabulário fechado | enums do `.schema.json` = constantes no BA (teste trava) |
| URL / env do cliente | `ITCS_FEEDBACK_TRIAGE_URL` · `ITCS_HEALTH_NORMALIZE_URL` · fallback `LLM_API_URL` → `…/feedbackTriage` |
| Expectativa em uma página | [EXPECTATIVAS.md](EXPECTATIVAS.md) |
| RAG por porta | [rag/RAG_PORTAS.md](rag/RAG_PORTAS.md) |
