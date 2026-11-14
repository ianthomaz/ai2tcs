# Changelog

O que muda no serviço, por publicação. Cada entrada diz o que muda para quem chama a API e,
em **Atenção no deploy**, o que precisa acontecer no servidor para valer. A seção
«Não publicado» é o que está na `main` (ou no ramo aberto) e ainda não subiu no mini62; no
deploy ela ganha a data e começa outra vazia.

## Não publicado

### Atenção no deploy

1. Antes do `git pull` no mini62: `git status`; arquivo mexido no servidor → `git stash`.
2. Migration nova `20261112120000_second_opinions` (entra ao subir o container). `SECOND_OPINION_WORKER_TOKEN`
   no `.env` só quando for ligar o worker; `SECOND_OPINION_NOTIFY_URL=http://host.docker.internal:9191/notify`
   quando o worker estiver em `--listen`. A referência do portão (`--save-baseline`) muda de sentido com
   os tipos de caso: gravar de novo.
   Demais: Variáveis novas opcionais (vazias = desligado): `DOC_EXTRACT_FALLBACK_PROVIDER`,
   `DOC_EXTRACT_FALLBACK_MODEL` e a chave do provedor escolhido.
3. Quem lê `/metrics` passa a mandar o token do operador.

### Novo

- **`/second-opinion`** ([docs/26](docs/26-second-opinion.md)): fila genérica (qualquer projeto e
  canal) em que um agente maior avalia a resposta da LLM local. Só leitura. Desligada até
  `SECOND_OPINION_ENABLED=true` **e** `config_json.second_opinion.enabled` no projeto; teto
  `SECOND_OPINION_DAILY_LIMIT` (20). Worker do host: `scripts/second_opinion_worker.py`
  (`--listen` atende a campainha que a API toca ao enfileirar; prompt em arquivo na pasta
  temporária; consulta só leitura do caso no sistema do projeto, com a chave 2 e sem dado pessoal).
- **Avaliação por tipo de caso:** cada caso de `eval_questions.json` pode ter `bucket`
  (`org_factual` · `org_link` · `user_system` · `silence` · `unsorted`); silêncio certo conta
  como acerto, e o portão mostra a conta por tipo. Os 85 casos do Bike Anjo estão classificados.
- **Leitura de NF e boleto diz quem leu:** `llm_reading` = `local` · `fallback` · `unavailable`
  (`unavailable`: a LLM caiu e só a heurística respondeu).
- **Reserva para a leitura de documento:** `DOC_EXTRACT_FALLBACK_PROVIDER` usa um provedor externo
  só quando a LLM local cai. Desligada; o texto do documento vai para o provedor, ligar é decisão do dono.

### Muda

- **Segunda opinião, uma conversa por pessoa:** o worker passa o `subject_ref` ao agente só no ambiente
  (`SECOND_OPINION_SUBJECT_REF`); o runner da Antigravity guarda uma conversa do professor por `user_id`
  (sem conta, uma geral) em `second_opinion_teacher_state.json`. O arquivo de estado de conversa única é
  ignorado: as conversas renascem por pessoa.

- **Segunda opinião:** `local_answer_rating` usa a escala do painel do projeto: `stop` · `bad` ·
  `good` · `great` (sai `neutral`). `/second-opinion/stats` soma `good` + `great` em `local_good` e
  `bad` + `stop` em `local_bad`.
- **Uma pasta por projeto** ([docs/27](docs/27-projetos-e-aprendizado.md)): `llm_api/project_library/{project_id}/`
  com manifesto, `diretrizes/` e `casos/eval_questions.json`; regras comuns em `_shared/regras-da-casa.md`.
  Os casos de avaliação saíram de `tests/eval/eval_questions.json` para a pasta de cada projeto
  (`eval_rag.py`, `eval_gate.py` e `import_eval_set.py` leem e gravam lá; `--dataset` aponta um arquivo só).
  `create_project.py` cria a pasta no formato novo (`rag/`, `diretrizes/`, `casos/`). A postura do Bike Anjo
  está em `project_library/bikeanjoall_2026/diretrizes/` (o seed lê; mesmo texto).
- **Segunda opinião:** o caso aceita `subject_ref` (id da pessoa no projeto, nunca telefone), que vai
  só para a consulta do worker; resposta da consulta até 16 KB; o professor julga com o que consultou e
  não repete à pessoa.
- **Professor = Antigravity** ([treinamento-llm/antigravity-no-mini62](docs/treinamento-llm/antigravity-no-mini62.md)):
  o prompt traz as regras da casa e as diretrizes do projeto (`project_library/`); worker com `--try caso.json`
  (um caso de arquivo, sem API), variáveis em `local-only/second_opinion_worker.env`, launchd de exemplo.
- **Worker da segunda opinião:** arquivo `local-only/DISABLE_SECOND_OPINION` pausa no host; API fora do ar
  para a drenagem; timeout padrão 180 s. Professor via
  `scripts/antigravity_agent_runner.py` (HTTP local + transcript JSONL; sem `agy` CLI).
- **`/health` sem chave** responde só `status` e `uptime_seconds`; com chave, também `checks`.
  **`/metrics`** exige o token do operador.
- **Áudio de formato desconhecido é recusado** (400); MP3 reconhecido em todas as variantes de quadro.

## 2026-11-11 — ops observe + OAuth fix (mini62)

### Atenção no deploy

1. `./scripts/deploy_llm.sh` (rebuild API).
2. Definir `OPS_OBSERVE_TOKEN` no `llm_api/.env` (≥ 32 caracteres). Sem token a rota
   responde 404 (stealth). Nome operacional desta chave no mini62: **claudeObserver**.
3. Conferir: `GET /api/ops/observe?view=health` com Bearer → 200; sem Bearer → 404.
4. Sem migration nova neste passo.

### Novo

- **`GET /api/ops/observe`** ([docs/24](docs/24-ops-observe.md)): observação remota só-leitura
  (logs redigidos + views SQL catalogadas). Auth: Bearer `OPS_OBSERVE_TOKEN`.


### Muda

- **Dashboard Google OAuth:** `google_oauth_start` recebe `Request` (cookie `secure` deixa
  de 500).

## 2026-11-10 — ratings, signals, busca, intent no ar (mini62)

### Atenção no deploy

1. Migration `20261110120000_answer_ratings` (aplicada no `prisma migrate deploy`).
2. Seed `bikeanjoall_2026` + ingest (corte novo dos trechos).
3. Subir junto com o Bike Anjo no mesmo contrato.
4. Portão: `eval_gate.py --project bikeanjoall_2026` (baseline se ainda não existir).

### Novo

- **`/ratings`** ([docs/22](docs/22-answer-ratings.md)): julgamentos → propostas → termos
  aprovados; exemplos `great` no `/ask` se `policies.rated_examples` (padrão desligado).
- **`signals`:** `grounding`, `unsupported_links`, `answer_confidence`, `confidence_basis`.
- **`GET /health?strict=1`:** 503 quando degradado.
- **Busca:** `retrieval_hints`, pool 2×`top_k`, chunking com overlap/título; flags
  `embedding_query_instruction` e `retrieval_query_with_history` (desligadas).
- **`intent` no `/ask`** (já no ar desde 30/out): corte `user_system` / `org_general`.

### Muda

- `rated_examples` chega de facto ao `/ask`; dashboard endurecido; áudio `.webm`;
  dedup `/ask` por pessoa+contexto; seed BA preserva termos aprovados; docs 21–23;
  triage-v2 regra 10; contrato BA sincronizado.
