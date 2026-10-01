# Contratos Bike Anjo × ai2tcs — em arquivo

Toda porta que o Bike Anjo usa (ou vai usar) no ai2tcs tem o contrato **aqui**, em
arquivo que os dois repositórios leem — não só em prosa. Quando prosa e arquivo
discordarem, **vale o arquivo**.

| Ler primeiro | Conteúdo |
|---|---|
| Este README | inventário, gap vs serviço vivo, padrão comum, como mudar |
| [`CHECKLIST_AI2TCS.md`](CHECKLIST_AI2TCS.md) | ordem de trabalho na sessão do ai2tcs + critérios de pronto |
| [`EXPECTATIVAS.md`](EXPECTATIVAS.md) | pedido / resposta / falhas — uma página por porta nova |
| [`prompts/`](prompts/) | rascunho de system prompt (`prompt_version`) + few-shots de triagem |
| [`rag/`](rag/RAG_PORTAS.md) | manifest do corpus, boost/downrank, intent clusters, docs `34`/`35` |
| Prosa | [10h](../../10h_ai2tcs_portas_de_texto.md) (molde) · [10g](../../10g_feedback_triage_llm.md) · [10f](../../10f_health_normalize_api_contract.md) · [10b](../../10b_nf_extract_api_contract.md) · [10d](../../10d_ai2tcs_contrato_e_evolucao.md) |
| Ensaios / lotes | [`runs/`](runs/README.md) — resultados versionados (ex. [2026-09-28 mini62](runs/2026-09-28-mini62-batch/NOTES.md): timeouts, fila calma) |

---

## Inventário × serviço vivo (mini62)

Rotas registradas em `ai2tcs/llm_api/app/main.py`. As três portas novas estão
**implementadas** no ai2tcs (branch `claude/bike-anjo-llm-integration-7fsuhp`, módulo
`llm_api/app/bikeanjo/`, doc `ai2tcs/docs/18-bikeanjo-ops-ports.md`) e **ainda não
publicadas** no mini62 — o serviço vivo segue sem elas até o deploy e o eval (ver
[CHECKLIST](CHECKLIST_AI2TCS.md) § Pôr no ar).

| Porta | Neste repo | No ai2tcs hoje | Cliente Bike Anjo |
|---|---|---|---|
| `POST /nfExtract` | esquema + exemplos | **produção** (`api/nf_extract.py`) | `itcs-nf-extract.ts` · zap |
| `POST /boletoExtract` | esquema + exemplos | **produção** (`api/boleto_extract.py`) | `itcs-boleto-extract.ts` |
| `POST /router` | esquema + exemplos | **produção** (`api/message_router.py`) | `zapzap/lib/llm-remote.js` |
| `POST /ask` (+ status/result) | esquema + exemplos | **produção** (`api/ask.py`) | idem |
| `POST /extract` · `/extract-multi` | esquema | **produção** (`api/extract.py`) | zap |
| `GET /health` | — | **produção** | smoke |
| `POST /feedbackTriage` | esquema + exemplos + eval + prompt | **implementada, não publicada** | `itcs-feedback-triage.ts` (fila `feedback_triage`) |
| `POST /healthNormalize` | esquema + exemplos + eval + prompt | **implementada, não publicada** | `itcs-health-normalize.ts` (fila `health_normalize`) |
| `POST /replySuggest` | esquema + exemplos + eval + prompt | **implementada, não publicada** | `itcs-reply-suggest.ts` (`/admin/suporte` → Responder) |
| erro comum | `common.schema.json` | NF/boleto mandam `errors:[]`; `error` ao lado é aceito | todos os clientes leem `error.message`, depois `errors[0]` |

Outras rotas no serviço que **não** têm pasta aqui (fora do escopo Bike Anjo ops):
`/edu/*`, `/audio/*`, `/nabilvideomap/qualify-caption`, `/ingest/*`, dashboard.

---

## Inventário de arquivos

| Porta | Esquema | Exemplos | Avaliação | Prompt rascunho |
|---|---|---|---|---|
| `/nfExtract` | `nf-extract.schema.json` | `nf-extract.examples.json` | — | (já no serviço) |
| `/boletoExtract` | `boleto-extract.schema.json` | `boleto-extract.examples.json` | — | (já no serviço) |
| `/router` | `router.schema.json` | `router.examples.json` | shadow → eval set | (já no serviço) |
| `/ask` | `ask.schema.json` | `ask.examples.json` | idem | (já no serviço) |
| `/extract` | `extract.schema.json` | — | — | (já no serviço) |
| `/feedbackTriage` | `feedback-triage.schema.json` | `feedback-triage.examples.json` | `feedback-triage.eval.jsonl` | `prompts/feedback-triage-v1.md` |
| `/healthNormalize` | `health-normalize.schema.json` | `health-normalize.examples.json` | `health-normalize.eval.jsonl` | `prompts/health-normalize-v1.md` |
| `/replySuggest` | `reply-suggest.schema.json` | `reply-suggest.examples.json` | `reply-suggest.eval.jsonl` | `prompts/reply-suggest-v1.md` |
| erro | `common.schema.json` | — | — | — |

---

## Acesso — só a chave do projeto

O ai2tcs dá a cada projeto uma chave `itcs_<project_id>_<24 hex>` que só serve a ele. O
Bike Anjo usa **só** a chave `itcs_bikeanjoall_2026_…` — decisão do dono, 28/set/2026. O
token global do serviço fica para os projetos que ainda não migraram.

| Onde | O que vale |
|---|---|
| Todas as portas no cliente Bike Anjo | `resolveBikeAnjoProjectKey` — sem a chave do projeto **não chama** (`token_missing` / `token_not_project_key`) |
| `/feedbackTriage`, `/healthNormalize`, `/replySuggest` no ai2tcs | só a chave do projeto (global → 403) |
| `/ask`, `/router`, `/extract`, `/nfExtract`, `/boletoExtract`, `/ingest` no ai2tcs | global ainda aceito até `SCOPED_KEY_REQUIRED_PROJECTS=bikeanjoall_2026` — o cliente já não envia global |

Porta única no código: `sistemaBA/src/lib/itcs-token.ts` · `zapzap/lib/itcs-token.js`.

**`.env` que levam a chave** (sistemaBA prod/stage, `ignore/zapzap.env.prod`, `zapzap/.env`,
env do `llm-ingest-bikeanjo.sh`): `LLM_API_TOKEN`, `ITCS_NF_EXTRACT_TOKEN` e, se
definidos, `ITCS_FEEDBACK_TRIAGE_TOKEN` / `ITCS_HEALTH_NORMALIZE_TOKEN`.

**Estado (28/set/2026):** a chave `itcs_bikeanjoall_2026_…` já está nos `ignore/env.*`,
`ignore/zapzap.env.*`, `sistemaBA/.env.local` e `zapzap/.env.local` **neste Mac e no
mini62**. Os **servidores** (Hetzner stage / `baOracle3a` prod) ainda têm o token global
até o próximo `sync-env`.

**CRITICAL — no próximo deploy (stage ou prod):**

1. Confirmar que `ignore/env.stage` / `ignore/env.prod` e os `zapzap.env.*` no mini62
   já trazem `itcs_bikeanjoall_2026_…` (não o token global de 48 hex).
2. Rodar `./start.sh sync-env-stage --zap` ou `sync-env-prod --zap` **antes** (ou junto)
   do rsync de código — senão o PM2 sobe com código novo e token velho.
3. Depois do sync: PM2 precisa reler o `.env` (restart do processo). Só editar o arquivo
   no disco do servidor **não** basta.
4. Só então, no ai2tcs: `SCOPED_KEY_REQUIRED_PROJECTS=bikeanjoall_2026` e restart.
   Sem o sync-env do Bike Anjo antes, o corte no ai2tcs derruba Zap / NF / boleto.

**Ordem do corte** (invertida, o bot do Zap para de responder):

1. Gerar a chave no Dashboard do ai2tcs (Projetos → `bikeanjoall_2026` → Chaves API) —
   já feita (label `sistemaBA-env-2026-09`; raw em `ignore/itcs-bikeanjoall-key.local`).
2. Pôr a chave em todos os `.env` locais / `ignore/` — **feito** Mac + mini62.
3. **No próximo deploy:** `sync-env` stage/prod + restart PM2 (passo CRITICAL acima).
4. No `.env` do ai2tcs: `SCOPED_KEY_REQUIRED_PROJECTS=bikeanjoall_2026` e restart.
   Os outros projetos seguem híbridos (ai2tcs `docs/02-api-integration.md § 2.1`).

## Formato — JSON

O fio fica em JSON. O modelo não lê o fio; a entrada que chega a ele já vai em JSON
compacto e sem ids, e a saída usa decodificação restrita a JSON (`format: "json"` no
Ollama). YAML economizaria pouco token e traria erro de indentação e de tipo na saída do
modelo. Detalhe: `ai2tcs/docs/18-bikeanjo-ops-ports.md` § 6.

---

## Os três tipos de arquivo (+ prompt)

- **`*.schema.json`** — JSON Schema 2020-12 com `$defs.request`, `$defs.response_ok` e
  `$defs.response_error`. No ai2tcs: gerar pydantic / validar com `jsonschema`.
- **`*.examples.json`** — `build_input` (montador BA) → `request` (wire) → `response_ok`
  (esperado). Teste de contrato: aceitar todo `request`; devolver molde de `response_ok`.
- **`*.eval.jsonl`** — uma linha por caso (`expect` + `why`). Calibração de prompt; não é
  teste determinístico — mede taxa. Critérios de pronto: [CHECKLIST](CHECKLIST_AI2TCS.md).
- **`prompts/*-v1.md`** — system prompt sugerido; a string `prompt_version` na resposta
  (`triage-v1`, `health-v1`, `reply-v1`) tem de bater com o arquivo usado.

---

## Padrão comum

O que toda porta **nova** de texto segue. As mais antigas diferem — a diferença **não**
se corrige quebrando cliente: entra ao lado, o cliente passa a ler o novo, e só então
o velho sai.

| Regra | Novas (triagem, saúde, reply) | Documento (NF, boleto) | Zap (router, ask) |
|---|---|---|---|
| Auth `Bearer`; projeto pelo token | sim | sim (+ `project_id` opcional no multipart) | sim |
| Campo desconhecido ignorado | sim | sim | sim (10d P1) |
| `status: "ok"` \| `"error"` | sim | sim | não — router sem `status`; ask pelo job |
| Erro de conteúdo em HTTP 200 | `error: { code, message }` | `errors: [mensagem]` (`legacy_error`) | `no_answer` / corpo vazio |
| Ausente é `null` | sim | sim | sim |
| `confidence` 0–1 | sim | não | router sim |
| `prompt_version` + `model` | **obrigatório** | não | não |
| Contato fora do texto | `llm-redact.ts` no BA **antes** de sair | N/A (documento) | não (mensagem da pessoa) |
| RAG | só `/replySuggest` (índice do bot) | não | `/ask` sim |

**Convergência futura (aditiva):**

1. NF/boleto: devolver `error: { code, message }` **ao lado** de `errors`. Os clientes
   (sistemaBA `itcsDocumentErrorMessage`, Zap `nfErrorMessage`) já leem
   `error.message` e, sem ele, `errors[0]`; falta o serviço mandar. `errors` sai depois.
2. NF/boleto/router: passar a devolver `prompt_version`.
3. Router: `confidence` só número (já coerente no serviço desde abr/2026).

---

## Quem garante o quê

| Lado | Garantia | Onde |
|---|---|---|
| sistemaBA | listas fechadas = código | `ai2tcs-contracts.test.ts` |
| sistemaBA | `build_input` → `request`; `response_ok` → normalize | idem |
| sistemaBA | texto livre sem e-mail/telefone/CPF | `llm-redact.ts` |
| zapzap | chaves de contexto router/ask no esquema | `ai2tcs-contracts.test.js` |
| ai2tcs | aceita todo `request` dos exemplos; resposta valida `response_ok` | `tests/test_bikeanjo_ops_contract.py` |
| ai2tcs | travas que não dependem do modelo (grave, saúde escrita, promessa, link) | `tests/test_bikeanjo_ops_rules.py` |
| ai2tcs | taxa no `*.eval.jsonl` antes de subir `prompt_version` | `scripts/eval_bikeanjo_ops.py` (serviço vivo) |

---

## Mudar o contrato

1. Campo novo **opcional** na resposta → esquema; cliente ignora até usar.
2. Valor novo em lista fechada → esquema **e** constante no mesmo commit (teste falha se só um).
3. Contexto novo no Zap → `ROUTER_CONTEXT_KEYS` / `ASK_CONTEXT_KEYS` **e** esquema **e** inject no prompt ai2tcs.
4. Quebra → rota ou `$id` com `/2`; antiga fica até migrar.
5. Prompt mudou → `prompt_version` novo; BA grava a versão ao lado do resultado.

---

## Enquanto os repositórios estão separados

O ai2tcs **não** lê este git. Na sessão com os dois lado a lado:

```text
docs/contracts/ai2tcs/  →  ai2tcs/llm_api/contracts/bikeanjo/
```

Anotar no README do destino o **commit SHA** deste repo. Mudança de contrato = um
commit em cada lado com o mesmo conteúdo. Passo a passo: [CHECKLIST_AI2TCS.md](CHECKLIST_AI2TCS.md).
