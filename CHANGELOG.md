# Changelog

O que muda no serviço, por publicação. Cada entrada diz o que muda para quem chama a API e,
em **Atenção no deploy**, o que precisa acontecer no servidor para valer. A seção
«Não publicado» é o que está na `main` (ou no ramo aberto) e ainda não subiu no mini62; no
deploy ela ganha a data e começa outra vazia.

## Não publicado

### Atenção no deploy

1. Antes do `git pull` no mini62: `git status`; arquivo mexido no servidor → `git stash`.
2. Sem migration. Variáveis novas opcionais (vazias = desligado): `DOC_EXTRACT_FALLBACK_PROVIDER`,
   `DOC_EXTRACT_FALLBACK_MODEL` e a chave do provedor escolhido.
3. Quem lê `/metrics` passa a mandar o token do operador.

### Novo

- **Leitura de NF e boleto diz quem leu:** `llm_reading` = `local` · `fallback` · `unavailable`
  (`unavailable`: a LLM caiu e só a heurística respondeu).
- **Reserva para a leitura de documento:** `DOC_EXTRACT_FALLBACK_PROVIDER` usa um provedor externo
  só quando a LLM local cai. Desligada; o texto do documento vai para o provedor, ligar é decisão do dono.

### Muda

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
