# 18 — Portas de operação do Bike Anjo (`/feedbackTriage`, `/healthNormalize`, `/replySuggest`)

Três portas de análise de texto **exclusivas do Bike Anjo**. Não são superfície pública
do ai2tcs: só entra a chave do projeto `bikeanjoall_2026`. Token global e chave de
qualquer outro projeto recebem **403**.

| | |
|---|---|
| Código | `llm_api/app/bikeanjo/` (`routes.py` + uma porta por arquivo + `common.py`) |
| Contrato (vale o arquivo) | `llm_api/contracts/bikeanjo/` — cópia de `bikeanjo2026all/docs/contracts/ai2tcs/`, origem em `ORIGIN.md` |
| Testes | `tests/test_bikeanjo_ops_contract.py` (exemplos × esquema, acesso, envelope) · `tests/test_bikeanjo_ops_rules.py` (travas) |
| Eval do modelo | `llm_api/scripts/eval_bikeanjo_ops.py` — roda os `*.eval.jsonl` no serviço vivo |
| Cliente | sistemaBA: `itcs-feedback-triage.ts`, `itcs-health-normalize.ts`; `/replySuggest` ainda sem cliente |

---

## 1. Para que serve cada uma

| Porta | Entrada | Devolve | RAG |
|---|---|---|---|
| `POST /feedbackTriage` | feedback de EBA, histórico de ciclista, **chamado de suporte** (contato do site, bug) | notas 1–5 (`text_quality`, `information_value`, `answer_solidity`), tags, `urgency`, âncora, nomes citados | não |
| `POST /healthNormalize` | resíduo de saúde que a taxonomia não mapeou | códigos da lista fechada + `outras` limpo + `generic_statement` | não |
| `POST /replySuggest` | chamado de suporte | rascunho de resposta **em shadow** (ninguém recebe), ou `no_answer` | sim, índice `bikeanjoall_2026` |

A priorização semanal/mensal (o que destacar para a equipe) é montada no Bike Anjo a
partir das notas, tags e urgência que a triagem devolve item a item — o serviço
classifica, não agrega.

---

## 2. Acesso

| Quem chama | Resultado |
|---|---|
| sem `Authorization` / token inválido | 401 (de `require_token`) |
| chave `itcs_bikeanjoall_2026_…` | entra |
| token global `LLM_API_TOKEN` | 403 |
| chave de outro projeto | 403 |
| chave do Bike Anjo nomeando outro projeto (body, `X-Project-Id`, path, query) | 403 |

Nas rotas antigas (`/ask`, `/router`, `/extract`, `/nfExtract`, `/boletoExtract`,
`/ingest`) o Bike Anjo sai do token global pela migração híbrida de
[02 § 2.1](./02-api-integration.md): com os clientes na chave do projeto,
`SCOPED_KEY_REQUIRED_PROJECTS=bikeanjoall_2026` no `.env` da API fecha o global para ele.

Configuração (`app/config.py`, todas com padrão):

| Variável | Padrão | O quê |
|---|---|---|
| `BIKEANJO_OPS_PROJECT_IDS` | `bikeanjoall_2026` | projetos cuja chave entra (vírgula) |
| `BIKEANJO_OPS_MODEL_ALIAS` | `smart` | alias do modelo (`fast`/`compact`/`smart`/`reasoner`) |
| `BIKEANJO_OPS_TIMEOUT_S` | `45` | abaixo dos 60 s do cliente BA |
| `BIKEANJO_OPS_NUM_PREDICT` · `BIKEANJO_OPS_TEMPERATURE` | `700` · `0.1` | orçamento de saída |
| `BIKEANJO_REPLY_RAG_CONTEXT_MAX_CHARS` | `6000` | teto do contexto RAG do `/replySuggest` |

O provedor segue o do projeto (`config_json.llm_provider`, padrão Ollama).

---

## 3. Molde comum

- JSON síncrono: uma chamada, uma resposta. Campo desconhecido é ignorado.
- Sucesso: `status: "ok"` + campos da porta + `confidence` 0–1 + `model` + `prompt_version` + `warnings`.
- Erro de conteúdo: **HTTP 200** com `{"status":"error","error":{"code","message"}}`,
  `code` ∈ `invalid_request` · `timeout` · `model_error` · `unauthorized`.
- O modelo roda com `format: "json"` (Ollama restringe a saída a JSON); resposta que não
  é JSON, ou sem os campos obrigatórios, é pedida de novo uma vez com a lista do que falta.
- Os system prompts são lidos de `contracts/bikeanjo/prompts/*-v1.md` (o texto abaixo da
  primeira linha `---`). Mudar o prompt é mudar o arquivo e o `prompt_version`.
- A entrada vai ao modelo em JSON compacto e **sem ids** (`submission_id`, `user_id`,
  `event_id`, `person.id` ficam fora do prompt).

---

## 4. Travas do serviço (valem qualquer que seja a resposta do modelo)

**`/feedbackTriage`**

- Tag fora da lista fechada sai (`warnings: tag_dropped:…`); urgência inválida vira `none`.
- `grave` → `urgency: urgent`, sempre. Texto com assédio, abuso, agressão, sangramento,
  ameaça, racismo etc. ganha `grave` mesmo quando o modelo não marca
  (`grave_by_keyword`) — recall antes de precisão: é sinal para uma pessoa ler.
- Nome em `named_people` só fica se estiver escrito no texto; `elogio_pessoa` sem nome
  vira `elogio_geral`.
- `anchor_quote` ≤ 160, tirado de algum campo, sem `[contato]`/`[documento]`; âncora que
  não existe no texto é trocada pela primeira frase do campo mais longo.

**`/healthNormalize`**

- Código fora de `diabetes · hypertension · asthma · renal · tdah · tea · t21` vai para `outras`.
- **A regra que não pode falhar:** o modelo marcar `generic_statement` num texto que
  cita condição, alergia, limitação ou remédio é revertido (`generic_statement_overridden`)
  e o texto fica em `outras`. Nada mapeado e nada limpo → `outras` guarda o texto da pessoa.
- `outras` no padrão de comparação: caixa baixa, itens separados por `", "`, cada item
  uma vez, sem moldura («tenho», «sou», «tomo»).

**`/replySuggest`**

- Chamado grave (assédio, violência, ameaça) **não chega ao modelo**: `no_answer`, `model: "guard"`.
- Sem trecho do corpus acima do limiar → `no_answer` sem chamar o modelo.
- Rascunho que promete ação («já excluí», «vou te enviar», «com sucesso»), traz `magic=`,
  link fora de `bikeanjo.org` e seus subdomínios, e-mail que não é
  `contato@bikeanjo.org` ou telefone → vira `no_answer` com `warnings: blocked:…`.
- `sources` só com documentos que a busca de fato trouxe.
- Ordem do contexto: `rag/retrieval-hints.json` → `ports.replySuggest` (boost −0,05 nos
  docs de suporte/FAQ/contato; +0,08 em estatuto, carta, regimento, `mapaFluxosLLM` e
  identidade do bot).

---

## 5. O que o Job guarda

Cada chamada vira uma linha terminal em `Job` (painel `/dashboard`), `job_kind`
`bikeanjo_feedback_triage` · `bikeanjo_health_normalize` · `bikeanjo_reply_suggest`.
Guarda-se **só rótulo**: tags, urgência, notas, `no_answer`, fontes, `prompt_version`.
Nenhum texto da pessoa, âncora, nome, código de saúde nem id de pessoa na saúde.

---

## 6. JSON, não YAML

Avaliado e mantido JSON:

1. O fio HTTP entre sistemaBA e ai2tcs não passa pelo modelo — trocar o formato ali não
   economiza token nenhum e quebraria os clientes e os esquemas.
2. Onde o token conta (entrada e saída do modelo), a entrada já vai em JSON compacto
   (sem indentação), que fica perto do YAML em tamanho.
3. Na saída, JSON tem decodificação restrita no Ollama (`format: "json"`) e parse sem
   ambiguidade. YAML gerado por modelo erra indentação e tem armadilhas de tipo
   (`no` → `false`, `1.10` → número) — o que se ganharia em token se perde em repetição.

---

## 7. Pôr no ar (mini62)

1. `git pull` do ai2tcs e rebuild do container (`./scripts/deploy_llm.sh`).
2. Smoke: `curl -X POST …/healthNormalize` com a chave do Bike Anjo e um `request` de
   `health-normalize.examples.json`; e com chave de outro projeto → 403.
3. Eval: `LLM_API_TOKEN=itcs_bikeanjoall_2026_… python scripts/eval_bikeanjo_ops.py` —
   só sobe `prompt_version` / liga o lote no BA com **PRONTO** nas três.
4. `/replySuggest` depende do re-ingest do corpus com `34`/`35` (lado BA, `10a §3`).
5. Corte do global para o Bike Anjo, nesta ordem: (a) chave `itcs_bikeanjoall_2026_…` em
   todos os `.env` do Bike Anjo (lista em `bikeanjo2026all/docs/contracts/ai2tcs/README.md`
   § Acesso); (b) deploy do Bike Anjo; (c) `SCOPED_KEY_REQUIRED_PROJECTS=bikeanjoall_2026`
   no `.env` da API e restart. Invertido, o bot do Zap para de responder.

<!-- [needsReview] a trava aceita bikeanjo.org e qualquer subdomínio (decisão do dono,
     28/set: medida média); o r07 do reply-suggest.eval.jsonl ainda proíbe qualquer
     "https://". Rascunho com https://sistema.bikeanjo.org passa na trava e reprova no
     eval. Rever o r07 quando o eval rodar no mini62; o dono decide. -->

---

## 8. Evolução — o que fica anotado, não feito

1. **Porta genérica de triagem de texto.** Classificar urgência, categoria e prioridade de
   feedback, chamado ou e-mail é o mesmo trabalho em qualquer projeto. O destino é uma
   porta única, multi-projeto, que receba o texto (inclusive e-mail que chegou fora do
   sistema), sugira o projeto quando não vier indicado, e devolva nível de urgência e
   categoria — um motor para todos, com o vocabulário de cada projeto por configuração.
   Até lá, `app/bikeanjo/` é exclusivo e um projeto novo não reaproveita estas rotas.
2. **E-mail como entrada do `/replySuggest`.** Um bot de e-mail (a construir) lê a caixa
   e usa a sugestão de resposta e a triagem para priorizar e categorizar mensagens.
   Pede o campo `channel: email` no contrato — mudança nos dois repositórios.
3. **`/ask` e `/replySuggest` com calma.** Hints de RAG e `intent_clusters` no `/ask`
   mexem no bot em produção: leva própria, com eval do `/ask` antes e depois.
4. **Treinar o modelo.** Os julgamentos 👍/👎 do shadow (bot e sugestões de chamado) são o
   conjunto de treino/eval de um ajuste futuro — projeto à parte.

---

**Anterior:** [17-integration-backlog.md](./17-integration-backlog.md)
