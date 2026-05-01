# 02 — Integração HTTP

Contrato da API LLM (auth, URLs, payloads). **NF Extract** (`/nfExtract`): [ManualNF_Extract](./refs/ManualNF_Extract). **Rede:** [refs/operacao-tailscale.md](./refs/operacao-tailscale.md). **Valores locais:** `local-only/` — [01-overview.md](./01-overview.md).

---

## Registo 2026-03

| Item | Onde |
|------|------|
| Meta-perguntas / RAG | § 4.5 |
| Troubleshooting (vazio, `no_answer`, orquestrador) | § 12 |
| Postgres: últimas mensagens Zap | § 14 |
| `POST /router`, zapzap: enviar `last_messages` / `recent_messages` | § 3.2 |
| WhatsApp: `tone_of_voice`, `message_size`, identidade na biblioteca | § 4.5 |
| Áudio: `POST /audio/transcribe`, `POST /audio/ask`; migração `20260323120000_job_audio_stt`; Docker com **ffmpeg** | § 3.7 |

## Registo 2026-04

| Item | Onde |
|------|------|
| `/edu/*` (chat, exercícios, Postgres); migração `20260403000000_edu_tables` | § 3.8, [06-edu-contract.md](./06-edu-contract.md) |
| Auth: `LLM_API_TOKEN` ou chave `itcs_<slug>_<hash>` (Dashboard → Chaves API); DB `20260408000000_api_keys_and_shared_libraries`, `20260408010000_add_job_model_alias` | [03-api-reintegration.md](./03-api-reintegration.md) |
| Aliases `fast`, `compact`, `smart`, `reasoner` | § 2, `app/config.py`, `.env.example` |
| `POST /router`: JSON novo (`action`, `confidence` numérico, `escalate_to`, …). Formato antigo (`confidence` string + só `suggested_route`) removido — actualizar clientes na mesma subida da API | § 3.2 |
| `POST /ingest/upload` | § 3, [03-api-reintegration.md](./03-api-reintegration.md) § 4 |
| `config_json.shared_libraries` | [03-api-reintegration.md](./03-api-reintegration.md) |

---

## 1. Visão geral

A API corre no **llm_server** (máquina onde a instalas; típico Mac ou Linux), porta **28471**. É a **mesma instância** em todos os caminhos abaixo; mudam só como o cliente **chega** até ela. Rede e Tailscale: [refs/operacao-tailscale.md](./refs/operacao-tailscale.md).

### 1.1 Duas formas de URL base (`LLM_API_URL`)

| Caminho | URL base típica | Quem usa |
|--------|------------------|----------|
| **A — Internet (HTTPS)** | `https://<teu-host-público-llm>` | Clientes **fora** da Tailscale quando expões HTTPS no edge (reverse proxy, TLS). Fluxo típico: cliente → TLS no edge → rede privada até o **llm_server** **:28471**. O valor exacto depende da tua infra — anota-o em `local-only/`. |
| **B — Tailscale (direto na API)** | `http://<IP-ou-hostname-na-tailnet>:28471` | Máquinas **na mesma tailnet**. Obtéis o IP com `tailscale ip -4` **no llm_server** (ou hostname no admin Tailscale). Ver [refs/operacao-tailscale.md](./refs/operacao-tailscale.md). |

**Auth e paths:** iguais nos dois casos — header `Authorization: Bearer` (§ 2) e os mesmos endpoints (`/ask`, `/nfExtract`, `/edu`, `/health`, etc.).

**Nota:** muitas instalações **não** expõem a porta 28471 diretamente à internet; o caminho A usa um proxy que termina TLS e encaminha para o **llm_server**. O caminho B evita isso dentro da tailnet.

**Fallback (VM em cloud sem TCP estável para peers Tailscale):** padrão **túnel SSH reverso** a partir do **llm_server** — script `llm_api/scripts/llm-tunnel-api-host-to-itcsvm.sh` (raiz do clone ou `llm_api/`); variáveis `ITCSVM_*` / `SSH_KEY` em env (`local-only/docs/`). No lado da VM, `LLM_API_URL=http://127.0.0.1:28471`. Detalhes em [refs/operacao-tailscale.md](./refs/operacao-tailscale.md) (secção 6).

**Dashboard:** interface web em `/dashboard`. **Preferência:** login **Google OAuth** — no `.env`: `DASHBOARD_GOOGLE_CLIENT_ID`, `DASHBOARD_GOOGLE_CLIENT_SECRET`, `DASHBOARD_OAUTH_REDIRECT_BASE` (sem `/` final; igual à origem no browser), e **`DASHBOARD_ALLOWED_EMAILS`** (obrigatório: pelo menos um e-mail em **minúsculas**; lista vazia impede qualquer login Google). Redirect canónico no GCP: `{DASHBOARD_OAUTH_REDIRECT_BASE}/dashboard/auth/google/callback`. Checklist: [refs/cloudflare-edge.md](./refs/cloudflare-edge.md); variáveis: [`.env.example`](../llm_api/.env.example). **Alternativa:** `DASHBOARD_USER` / `DASHBOARD_PASSWORD` só se OAuth **não** estiver completo (ou ambos, se quiseres fallback). O Bearer da API **não** serve para o HTML do dashboard.

**Deploy da API:** corre **neste computador**, só com Docker. Na raiz do repositório ai2tcs: `./scripts/deploy_llm.sh` (rebuild + `docker compose up -d --build api` em `llm_api/`). Não há deploy por SSH para outro host. Não usar `run_api.sh` nem launchd para produção.

### 1.2 Integração por projecto (estrutura, itcs-webplace, extensão)

Os contratos deste ficheiro são **partilhados** por todos os clientes (`Authorization`, `LLM_API_URL`, mesmos paths). O objectivo do mono-repo é expor **como pedir** e **como mapear** respostas — para cada novo produto **adaptar** o seu lado (SQLite, workers, UI), não listar aqui cada detalhe de negócio possível.

A instância e exemplos de produção alinhados com **itcs-webplace**; integradores noutro contexto usam os mesmos endpoints e tratam o **seu** `project_id` + biblioteca como isolamento lógico.

Quando um projecto precisa de **comportamento dedicado** (prompts, JSON adicional, rota nova, semântica de job), isso **negocia-se com a manutenção da API**: convém chegar com **pedido explícito** (rotas, exemplos de request/response, limites, idioma). A partir daí ajusta-se o fluxo (código + prompts + documentação) de forma coerente — ver também [01-overview.md](./01-overview.md) (secção *Integração: escopo, itcs-webplace e customização*).

**Exemplo — `POST /nabilvideomap/qualify-caption`:** corpo JSON mínimo `project_id`, `text` (legenda UTF-8), opcionais `use_rag`, `model` (aliases `fast`, `compact`, `smart`, `reasoner` ou nome Ollama). Resposta JSON com chaves fixas: `location_accuracy`, `location_granularity`, `location_primary_label`, `llm_location_candidates` (lista de `{label, kind, confidence}`), `location_ambiguity_notes`, `location_confidence`, `theme_primary`, `theme_secondary`, `theme_tags`, `llm_theme_notes`, `summary_140`. Enumerações exactas e semântica fina: **OpenAPI em `{LLM_API_URL}/docs`** no ambiente onde a API corre; variantes por produto combinam-se com a manutenção.

---

## 2. Autenticação

Todas as requisições à API REST (exceto `/health` e o que estiver explicitamente aberto) exigem o header:

```
Authorization: Bearer <token>
```

Há **dois** tipos de token válidos (o servidor aceita qualquer um deles):

| Modo | Valor no `Bearer` | Quando usar |
|------|-------------------|-------------|
| **Global (legado / admin)** | `LLM_API_TOKEN` do `.env` da API | Integrações já existentes; tens de enviar **`project_id` no corpo** (JSON ou form) quando o endpoint precisar dele. |
| **Chave por projeto** | Chave mostrada uma vez no Dashboard (**Projetos → [projeto] → Chaves API**), formato `itcs_<project_id>_<hex>` | Novos clientes; o `project_id` fica associado à chave. Se enviares `project_id` no corpo, **tem de coincidir** com o da chave senão `403`. |

Boas práticas: guarde o token em **variável de ambiente** no cliente — nunca em código versionado.

**Migração:** ver [`03-api-reintegration.md`](03-api-reintegration.md). Podes manter só o token global até migrares cada projeto à mão.

---

## 3. Endpoints

| Método | Path | Descrição |
|--------|------|-----------|
| POST | `/ask` | Enviar pergunta (retorna `job_id`, status 202) |
| GET | `/status/{job_id}` | Estado do job |
| GET | `/result/{job_id}` | Resposta final + fontes (apenas URLs externas, se houver); em jobs de áudio inclui `transcript` e `stt_metadata` (§ 3.7) |
| **POST** | **`/audio/transcribe`** | **Transcrição local (assíncrona)** — `multipart/form-data`; ver § 3.7 |
| **POST** | **`/audio/ask`** | **Áudio → texto → mesmo pipeline que `/ask`** — `multipart/form-data`; ver § 3.7 |
| **POST** | **`/extract`** | **Extração síncrona (zapzap onboarding)** — um campo por chamada; ver § 3.1 |
| **POST** | **`/extract-multi`** | **Extração multi-campo (zapzap)** — vários campos numa mensagem; ver § 3.1 |
| **POST** | **`/nfExtract`** | **Extração de nota fiscal (itcsNFextract)** — corpo **somente** `multipart/form-data`; exatamente **um** campo: `file` (upload) **ou** `server_file_path` **ou** `document_url` (nomes fixos). Manual: [ManualNF_Extract](./refs/ManualNF_Extract) §3.1. |
| **POST** | **`/nabilvideomap/qualify-caption`** | **Qualificação síncrona de legenda** (ex.: catálogo de conteúdo / nabilVideoMap) — JSON; auth § 2. Corpo e chaves de resposta: **§ 1.2**. Detalhe de prompts/RAG por ambiente: acordar com manutenção ou notas no clone privado. |
| **POST** | **`/router`** | **Roteador de mensagem** — ver § 3.2 (orienta: biblioteca vs fluxo; decisão é do orquestrador) |
| POST | `/ingest` | Indexar/reindexar biblioteca; cria projeto se não existir (com sources no body ou env) |
| **POST** | **`/ingest/upload`** | **Upload multipart** de um ficheiro para o disco do projeto (ou biblioteca partilhada) + fila de ingest incremental — ver [`03-api-reintegration.md`](03-api-reintegration.md) §4 |
| GET | `/projects` | Listar projetos — ver § 3.3 |
| GET | `/projects/{project_id}` | Detalhes de um projeto |
| POST | `/projects` | Criar projeto |
| PUT | `/projects/{project_id}` | Atualizar projeto |
| DELETE | `/projects/{project_id}` | Remover projeto |
| GET | `/jobs` | Listar jobs (filtros: project_id, status, limit, offset) — ver § 3.4 |
| GET | `/jobs/stats` | Estatísticas (total, por status, por projeto, últimas 24h) |
| POST | `/jobs/{job_id}/cancel` | Cancelar job em fila |
| PUT | `/users/profile` | Criar/atualizar perfil do usuário |
| GET | `/users/profile/{project_id}/{user_id}` | Consultar perfil |
| DELETE | `/users/profile/{project_id}/{user_id}` | Deletar perfil |
| POST | `/users/conversation/reset` | Resetar histórico de conversa |
| POST | `/users/conversation/maintenance` | Forçar resumo + limpeza mensal |
| GET | `/health` | Checar se API, Ollama e Postgres estão vivos |
| GET | `/metrics` | Métricas Prometheus — ver § 3.6 |
| GET | `/dashboard` | Interface web (login Google OAuth e/ou user/senha do `.env`) |
| POST | `/edu/chat` | Tutor **síncrono**; resposta sempre com `reply_structured` (modelo ou segmento fixo se falhar schema após retry) — § 3.8 |
| POST | `/edu/exercise` | Gerar exercícios a partir do nível ou de `vocab_ids` — § 3.8 |
| GET | `/edu/vocabulary` | Listar vocabulário (`language`, `level`, `limit`, `offset`) — § 3.8 |
| POST | `/edu/vocabulary` | Criar entrada de vocabulário — § 3.8 |
| GET | `/edu/grammar` | Listar pontos gramaticais — § 3.8 |
| POST | `/edu/grammar` | Criar ponto gramatical — § 3.8 |
| POST | `/edu/progress` | Registar acerto/erro por `user_id` + `vocab_id` (marcado **mastered** após 5 acertos) — § 3.8 |

### 3.1 POST /extract — Extração síncrona (zapzap)

Usado pelo **zapzap** quando a validação rígida do onboarding falha (ex.: usuário escreve "moro perto do metrô Sé" em vez do CEP). Uma chamada Ollama síncrona; resposta imediata.

**Request:**
```json
{
  "task": "extract",
  "step": "interesse | nome | cpf | email | nascimento | cep",
  "question": "Texto da pergunta que foi feita ao usuário",
  "userReply": "Resposta em texto livre do usuário"
}
```

**Response (200):**
```json
{ "extracted": "01310100" }
```
ou, quando não for possível extrair:
```json
{ "extracted": null }
```

**Formato esperado por step:** CEP e CPF só dígitos (8 e 11); interesse como "1" a "6"; nascimento `dd/mm/aaaa`; nome e email em texto. O cliente (zapzap) valida o valor com `step.validate(extracted)` antes de usar.

**Auth:** mesmo `Authorization: Bearer` do resto da API.

**Steps suportados (onboarding):** `interesse`, `nome`, `cpf`, `email`, `nascimento`, `cep`.

**Step extra (pedido de pagamento / zapzap):** `payment_nf_confirmation`

- Usado após a leitura da nota fiscal no WhatsApp: o usuário manda correções em texto livre (emissor, valor, `copiar: email@…`, PIX, banco, observações).
- O campo `question` traz o contexto montado pelo zapzap (inclui JSON `current_nf`).
- A resposta é **`extracted` como string JSON** (não um único valor escalar). Chaves permitidas (todas opcionais):  
  `supplier_name`, `amount`, `nf_number`, `payment_type` (`pix` \| `transferencia` \| `boleto` \| `dinheiro` \| `cartao_credito`), `payment_info`, `payment_freeform`, `pix_key`, `contact_email`, `bank_name`, `bank_agency`, `bank_account`, `internal_reference`, `context_notes`, `notes`.
- Se nada couber: `extracted` = `"{}"` ou `null` em erro de modelo.
- Modelo Ollama: alias **`smart`** (melhor aderência a JSON); `num_predict` maior que no onboarding.

#### 3.1.1 POST /extract-multi — vários campos de uma vez

Contrato alinhado ao zapzap (`LLM_API_CONTRACT.md` no repo bikeanjo/zapzap). O corpo inclui `task: "extract_multi"`, `userReply`, `fields` (lista de `{ id, label, example }`) e opcionalmente `context`.

**`context`:** além de `current_step` e `already_collected`, a API **aceita chaves extras** (sem descartar). No fluxo de pagamento o zapzap envia por exemplo `step`, `instruction`, `current_nf`, `message_lines` — tudo é repassado ao modelo em um único JSON para contextualizar a extração.

**Response (200):** `{ "extracted": { "nome": "...", "cpf": "..." } }` — só entradas extraídas com sucesso; objeto vazio se nada válido.

**Pagamento:** quando `context` indica confirmação de NF (ex.: `step: "payment_nf_confirmation"` ou presença de `current_nf`), o prompt reforça que podem ser correções de pagamento; com muitos `fields`, o limite de tokens de saída é ampliado automaticamente.

### 3.2 POST /router — Roteador de mensagem (triage + intenção)

**Endpoint ativo.** O orquestrador chama o roteador para decidir: (a) **responder já** com texto curto (`answer_now`), ou (b) **escalar** para um especialista (`escalate`) com sugestão de alias de modelo (`compact` / `smart` / `reasoner` / `auto`). Mantém o eixo **WhatsApp / zapzap** via `suggested_route` (intenção canónica). O roteador **só orienta**; quem executa é o orquestrador.

**URL:** `POST {LLM_API_URL}/router` (mesma base da API, porta 28471).

**Request (body JSON):**

| Campo | Obrigatório | Tipo | Descrição |
|-------|-------------|------|-----------|
| `message` | sim | string | Texto da mensagem recebida do usuário. |
| `project_id` | não | string | Slug do projeto. **Recomendado.** Com chave por projeto, deve coincidir com a chave (senão `403`). Sem `project_id`, a API devolve triagem genérica (`escalate` / `ask`). |
| `user_name` | não | string | Nome do usuário (quando o orquestrador tiver). |
| `user_registered` | não | boolean | Telefone já cadastrado no sistema. |
| `onboarding_active` | não | boolean | Usuário no meio do onboarding. |
| `onboarding_completed` | não | boolean | Onboarding já concluído. |
| `current_flow` | não | string | Id do fluxo em que o usuário está (ex.: `cadastro_basico_flow`). |
| `current_step` | não | string | Etapa atual dentro do fluxo. |
| `last_messages` | não | array de strings | Últimas N mensagens para contexto. |
| `model` | não | string | Alias ou nome Ollama para **esta** chamada de triagem: `fast` (default), `compact`, `smart`, `reasoner`, ou tag explícita. |

**Exemplo de request com contexto:**
```json
{
  "message": "Quero me cadastrar",
  "project_id": "bikeanjoall_2026",
  "user_name": "Maria",
  "current_flow": null,
  "current_step": null,
  "last_messages": ["user: Oi", "assistant: Olá! Em que posso ajudar?"]
}
```

**Response (200) — contrato actual (JSON da API):**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `action` | string | `answer_now` — a resposta curta vai em `answer`; `escalate` — seguir com especialista. |
| `suggested_route` | string | Intenção canónica zapzap: `ask`, `cadastro`, `saudacao`, `escalar_humano`, `documento`, `status`, `agradecimento`. |
| `answer` | string \| null | Texto em português se `action` = `answer_now`. |
| `escalate_to` | string \| null | `compact`, `smart`, `reasoner`, ou `auto` (o servidor pode resolver para um alias). |
| `obs` | string \| null | Nota curta para o especialista ou para log. |
| `task_type` | string \| null | Ex.: `chitchat`, `extract`, `rag_deep`, `reasoning`, `classification`. |
| `confidence` | number | `0.0` a `1.0` (não é mais string `high` / `medium` / `low`). |

**Exemplo de response (`escalate`):**
```json
{
  "action": "escalate",
  "suggested_route": "cadastro",
  "answer": null,
  "escalate_to": "smart",
  "obs": "Pedido explícito de cadastro; preparar fluxo de onboarding.",
  "task_type": "classification",
  "confidence": 0.92
}
```

**Exemplo de response (`answer_now`):**
```json
{
  "action": "answer_now",
  "suggested_route": "saudacao",
  "answer": "Olá! Sou a assistente do Bike Anjo. Em que posso ajudar hoje?",
  "escalate_to": null,
  "obs": null,
  "task_type": "chitchat",
  "confidence": 0.88
}
```

**Integração zapzap:** (1) Continuar a usar `suggested_route` para decidir fluxo vs `/ask`. (2) Usar `action`: se `answer_now`, podes devolver `answer` ao utilizador sem chamar `/ask`; se `escalate`, usar `escalate_to` / `obs` para escolher modelo ou ir directo a `/ask` com o contexto adequado. (3) Tratar `confidence` como número (thresholds no teu código).

**Compatibilidade:** versões antigas esperavam `confidence` como string e só três campos principais. **Antes de fazer deploy desta API em produção**, actualiza o orquestrador zapzap para o novo schema ou mantém uma versão anterior da API até ambos estarem prontos.

**Auth:** ver § 2 (`Bearer` global ou chave por projeto).

### 3.3 GET/POST/PUT/DELETE /projects — CRUD de projetos

Permite listar, criar, atualizar e remover projetos via API (alternativa ao seed/SQL). Todos os endpoints exigem token.

**Listar projetos — GET /projects**

Response (200):
```json
{
  "projects": [
    {
      "project_id": "webplacecc",
      "name": "WebPlaceCC",
      "sources": ["/caminho/bibliotecaLLM", "/caminho/mapaFluxosLLM"],
      "config_json": { "chunking": {...}, "policies": {...} },
      "themes": [],
      "created_at": "2026-03-06T10:00:00Z",
      "updated_at": "2026-03-06T10:00:00Z"
    }
  ],
  "total": 1
}
```

**Criar projeto — POST /projects** (201):
```json
{
  "project_id": "meu_projeto",
  "name": "Meu Projeto",
  "sources": ["/caminho/biblioteca", "/caminho/fluxos"],
  "config_json": null,
  "themes": []
}
```

**Atualizar projeto — PUT /projects/{project_id}** (200): mesmos campos (todos opcionais).

**Remover projeto — DELETE /projects/{project_id}** (204): sem body.

### 3.4 GET /jobs, GET /jobs/stats, POST /jobs/{job_id}/cancel — Jobs

**Listar jobs — GET /jobs**

Query params: `project_id` (opcional), `status` (opcional), `limit` (default 50), `offset` (default 0).

Response (200):
```json
{
  "jobs": [
    {
      "job_id": "550e8400-...",
      "project_id": "webplacecc",
      "question": "Qual o horário?",
      "status": "done",
      "progress": null,
      "answer": "O horário é...",
      "sources": [],
      "confidence": "high",
      "error_message": null,
      "created_at": "2026-03-06T10:00:00Z",
      "updated_at": "2026-03-06T10:00:05Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

**Estatísticas — GET /jobs/stats**

Response (200):
```json
{
  "total": 150,
  "by_status": { "done": 120, "queued": 2, "working": 1, "failed": 5 },
  "by_project": { "webplacecc": 80, "bikeanjoall_2026": 70 },
  "last_24h": 15,
  "avg_duration_seconds": 12.5
}
```

**Cancelar job — POST /jobs/{job_id}/cancel** (200): só jobs com `status: "queued"`. Response: `{"job_id": "...", "status": "cancelled"}`.

### 3.5 GET /dashboard — Interface web

Interface HTML (HTMX + Jinja2) para operação: listar projetos, jobs, estatísticas e health. Login: **Google** (`/dashboard/login` → `/dashboard/auth/google`) com **`DASHBOARD_ALLOWED_EMAILS` obrigatório** (allowlist não vazia, minúsculas), ou **usuário/senha** legado se OAuth não estiver completo. URL: `GET {LLM_API_URL}/dashboard`. GCP: **Authorized redirect URI** = `{DASHBOARD_OAUTH_REDIRECT_BASE}/dashboard/auth/google/callback` por origem (ex.: `http://127.0.0.1:28471/...`, `https://llm.webplace.cc/...`). Detalhe: [refs/cloudflare-edge.md](./refs/cloudflare-edge.md).

### 3.6 GET /metrics — Métricas Prometheus

Retorna métricas em formato Prometheus (texto). Exemplo:

```
llm_api_ready 1
llm_jobs_total 150
llm_jobs_last_24h 15
llm_jobs_by_status{status="done"} 120
llm_jobs_by_project{project="webplacecc"} 80
llm_jobs_avg_duration_seconds 12.5
llm_stt_completed_total 42
llm_stt_failed_total 1
llm_stt_transcribe_seconds_sum 180.5
llm_stt_transcribe_seconds_avg 4.298
```

Útil para monitoramento com Prometheus/Grafana. **Não exige** `Authorization` (verifique se sua instalação expõe `/metrics` ou protege via proxy).

### 3.7 POST /audio/transcribe e POST /audio/ask — STT local (Whisper)

Transcrição **local** com **faster-whisper** (modelos Whisper). O fluxo é **assíncrono** como o `/ask`: a API devolve **202** com `job_id` e o cliente faz polling em `GET /status/{job_id}` e `GET /result/{job_id}`.

**Auth:** mesmo header `Authorization: Bearer`.

**Formato:** `multipart/form-data` com:

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| `file` | sim | Áudio (extensões típicas: `.ogg`, `.mp3`, `.wav`, `.m4a`, `.webm`; limite padrão 25 MiB) |
| `project_id` | sim | Slug do projeto (deve existir) |
| `user_id` | não | Identificador do utilizador (ex.: telefone WhatsApp), para histórico em `/audio/ask` |
| `language` | não | Código de idioma para o STT (ex.: `pt`); vazio = deteção automática |

**POST /audio/transcribe** — só transcreve. No resultado final, `answer` e `transcript` repetem o texto transcrito; `stt_metadata` inclui `language`, `duration_seconds`, `segment_count`, `model`, `transcribe_seconds`.

**POST /audio/ask** — transcreve e depois executa o **mesmo pipeline RAG** que `POST /ask`, usando o texto transcrito como pergunta. Campos extra (todos opcionais, form fields):

| Campo | Descrição |
|-------|-----------|
| `model` | Alias `fast` / `smart` ou nome de modelo Ollama (igual a `/ask`) |
| `system_prompt` | Prefixo de sistema (igual a `/ask`) |
| `user_context_json` | JSON objeto — snapshot de contexto (nome, CEP, etc., como em `/ask`) |
| `history_json` | JSON array de `{ "role", "text" \| "content" }` — histórico recente (como `history` em `/ask`) |

**Exemplo (transcrever apenas):**

```bash
curl -s -X POST -H "Authorization: Bearer $LLM_API_TOKEN" \
  -F "project_id=bikeanjoall_2026" \
  -F "file=@/caminho/audio.ogg;type=audio/ogg" \
  "$LLM_API_URL/audio/transcribe"
```

**GET /result** em jobs de áudio: além de `answer` e `sources`, pode vir `transcript` e `stt_metadata` (útil para `/audio/ask`, onde `answer` é a resposta RAG e `transcript` é o que foi dito no áudio).

**Operação:** na primeira utilização o modelo Whisper é descarregado para `data/whisper_models` (ou `WHISPER_DOWNLOAD_ROOT`). Em CPU o tempo de transcrição depende do tamanho do áudio e do `WHISPER_MODEL_SIZE` (default `small`).

**Desativar STT:** `WHISPER_ENABLED=false` — os endpoints de áudio respondem **503**.

**Troubleshooting:** `stt:` no `error_message` do job — falha na transcrição (ficheiro corrupto, codec, modelo em falta, memória). Garantir **ffmpeg** no host (incluído na imagem Docker da API). Job `failed` com `empty transcript` — áudio sem fala detetável.

### 3.8 Eixo educacional — `GET`/`POST /edu/*`

Rotas para **aprendizagem de idiomas** (desenho atual centrado em **chinês** `zh-CN` e níveis tipo **HSK1**–**HSK6**). **Não usam RAG** nem biblioteca de projetos: o contexto pedagógico vem das tabelas Postgres `edu_vocabulary`, `edu_grammar` e `edu_progress`.

**Auth:** `Authorization: Bearer` (igual ao resto da API).

**Sincronismo:** cada rota faz **uma** chamada ao Ollama e devolve a resposta no mesmo request (não há `job_id`).

**Contrato e exemplos JSON completos:** [06-edu-contract.md](./06-edu-contract.md).

**Site / projeto chinês (Next.js, RAG, env):** **`local-only/docs/CHINESE_LEARNING_PROJECT.md`**.

| Rota | Função resumida |
|------|------------------|
| `POST /edu/chat` | Mensagem do aluno + `level` + `language` + `history` opcional → resposta estruturada (`reply_structured`, `full_reply_text`); validação + 1 retry + fallback fixo; ver [06-edu-contract.md](./06-edu-contract.md). |
| `POST /edu/exercise` | Gera exercícios (`fill_blank`, `translation`, etc.). Exige vocabulário: ou `vocab_ids`, ou `level`/`language` com linhas em `edu_vocabulary`. Se não houver dados, resposta **400** com mensagem do tipo *No vocabulary found*. |
| `GET`/`POST /edu/vocabulary` | Listar (paginado) ou criar itens (hanzi, pinyin, tradução, nível, exemplos). |
| `GET`/`POST /edu/grammar` | Listar ou criar regras (`pattern`, `explanation`, `examples` em JSON). |
| `POST /edu/progress` | `user_id`, `vocab_id`, `correct` — atualiza contagens; `mastered` fica **true** após **5** respostas corretas acumuladas (ver lógica em `app/edu/db.py`). |

**`POST /edu/chat` — resposta e consumo (Chinese Learning / UIs com toggles):**

- Em **HTTP 200**, o corpo inclui **`reply`**, **`full_reply_text`** e **`reply_structured`** (lista não vazia). O modelo pode falhar o schema; nesse caso a API tenta **retry** e, se preciso, devolve um **segmento fixo** (hanzi + PT a pedir nova tentativa) para o UI manter toggles por frase.
- O cliente deve renderizar por segmento (hanzi + pinyin + `translation.pt` / `en` / `es`); `en`/`es` podem vir vazios.
- **`POST /ask`** (RAG) não segue este formato; continua com **`answer`** em texto após o job. Apenas **`/edu/chat`** é o tutor chinês com resposta estruturada.

Exemplo:

```bash
curl -s -X POST "$LLM_API_URL/edu/chat" \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Olá, quero praticar saudações.","level":"HSK1","language":"zh-CN"}'
```

Detalhes de campos e normalização: [06-edu-contract.md](./06-edu-contract.md).

**Operação e deploy:** aplicar migração **`20260403000000_edu_tables`** (incluída no `prisma migrate deploy` ao subir o container). Após deploy, **popular vocabulário** antes de usar `/edu/exercise` em produção (via `POST /edu/vocabulary` ou SQL/seed).

**Limitação atual (transparente para integradores):** em `POST /edu/chat`, o campo `user_id` é aceite no modelo mas **ainda não** alimenta o prompt com o histórico de `edu_progress` (personalização por palavras fracas virá numa evolução). O registo de progresso em `/edu/progress` já persiste dados para esse uso futuro.

**Modelo LLM:** por defeito usa o alias **`smart`** do projeto (configurável com `model` no body onde o modelo Pydantic o permitir — ver contrato EDU).

---

## 4. Fluxo completo de pergunta

### 4.1 Request — `POST /ask`

```json
{
  "project_id": "bikeanjoall_2026",
  "question": "Qual o horário de funcionamento?",
  "user_id": "5511999990000",
  "user_context": {
    "name": "Maria Silva",
    "birth_date": "15/05/1990",
    "cep": "01310100",
    "city": "São Paulo",
    "state": "SP",
    "health": "Nenhuma restrição",
    "interesse": "aprender_a_pedalar",
    "registered": true
  },
  "history": [
    { "role": "user", "text": "oi" },
    { "role": "assistant", "text": "Olá! Como posso ajudar?" }
  ],
  "system_prompt": "Você é a assistente virtual do Bike Anjo..."
}
```

**Campos:**
- `project_id` (obrigatório): slug do projeto registrado no banco.
- `question` (obrigatório): a pergunta do usuário.
- `user_id` (opcional, recomendado): identificador do usuário final (ex.: telefone WhatsApp). Quando presente, a API mantém **contexto de conversa** no banco — pergunta e resposta são gravadas. Se `history` for enviado, esse histórico é usado **no prompt desta resposta** em vez do histórico lido do Postgres (útil para espelhar o fio do WhatsApp).
- `user_context` (opcional): nome, `birth_date` (DD/MM/AAAA ou ISO), CEP, cidade, estado, saúde, `interesse`, `registered` (zapzap). Personaliza a resposta; `interesse` e `registered` entram no bloco de perfil do prompt.
- `history` (opcional): lista de `{ "role": "user"|"assistant", "text": "..." }` (também aceita chave `content` em vez de `text`).
- `system_prompt` (opcional): texto enviado pelo cliente (persona WhatsApp); é **prefixado** ao system prompt interno de RAG/calibração.
- `hint` (opcional): dica para auto-router quando `project_id` é ambíguo.

### 4.2 Response — 202 Accepted

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Question received. Poll /status/{job_id}...",
  "status_url": "/status/550e8400-...",
  "result_url": "/result/550e8400-..."
}
```

### 4.3 Polling — `GET /status/{job_id}`

```json
{
  "job_id": "550e8400-...",
  "status": "working",
  "client_status": "processing",
  "progress": "generating",
  "created_at": "2026-03-06T10:00:00Z"
}
```

**Status possíveis (campo `status`):** `queued` → `working` → `done` | `no_answer` | `need_more_info` | `failed` | `cancelled`

**Campo `client_status`:** espelho para clientes zapzap — vale `processing` enquanto `status` for `queued` ou `working`; nos demais casos é igual a `status` (ex.: `done`, `failed`). Pode ser usado no polling no lugar de tratar `queued`/`working` separadamente.

### 4.4 Resultado — `GET /result/{job_id}`

```json
{
  "job_id": "550e8400-...",
  "status": "done",
  "answer": "O horário de funcionamento é de segunda a sexta, das 9h às 18h.",
  "sources": [
    { "url": "https://exemplo.com/sobre" }
  ],
  "confidence": "high",
  "transcript": null,
  "stt_metadata": null
}
```

Em jobs originados por **`/audio/ask`**, `transcript` contém o texto reconhecido no áudio e `stt_metadata` os metadados do STT; `answer` é a resposta do RAG. Em **`/audio/transcribe`**, `transcript` repete o texto e `answer` também (transcrição apenas).

**Campo `sources`:** a API **não** expõe caminhos de arquivo nem trechos internos da biblioteca (o usuário final não tem acesso a eles). Ela retorna apenas **referências externas** quando a biblioteca tiver URLs indicadas (sites, links). Cada item é `{ "url": "https://..." }`. Se não houver URLs na biblioteca para o contexto usado, `sources` vem como lista vazia `[]`. Para incluir links na resposta, a biblioteca indexada precisa fornecer o campo `url` no metadata dos chunks (ex.: via convenção no ingest).

### 4.5 Perguntas meta, existenciais e identidade ("Quem é você?")

O pipeline `/ask` é **RAG-first**: recupera trechos da biblioteca indexada e pede ao modelo que responda com base nisso. Perguntas como *"Quem é você?"*, *"O que é a consciência?"* ou *"Você tem sentimentos?"* muitas vezes **não batem bem** com os chunks (FAQ, estatuto, horários). O modelo pode:

- devolver resposta vazia ou `no_answer` / `need_more_info` (o orquestrador — ex. zapzap — mostra mensagem genérica tipo *"A assistente não conseguiu responder agora..."* se o utilizador tiver modo LLM ativo e a API não devolver texto);
- ou **alucinar** / soar estranho se o contexto recuperado for fraco ou irrelevante.

**Como melhorar de forma prática (Bike Anjo e projetos semelhantes):**

1. **Biblioteca:** adicionar um ficheiro curto e explícito, ex. `identidade-assistente.md`, com título claro (`Sobre: identidade da assistente`) e texto fixo: quem é a assistente (virtual do Bike Anjo), o que faz, que não é humana, tom amigável. **Reindexar** (`POST /ingest`) após criar/editar.
2. **`instrucoes-llm.md` no projeto** (se usar `behavior_instruction_path`): regra explícita — *"Se a pergunta for sobre quem você é ou o seu papel, responda em 2–3 frases como assistente virtual do [projeto], sem filosofia; não diga que está a ser treinado a menos que seja política comunicada."*
3. **`system_prompt` do cliente (WhatsApp):** deve **prefixar** a persona (já recomendado em § 4.1). Incluir linha dedicada: *"Perguntas sobre a tua identidade: explica que és a assistente virtual do Bike Anjo no WhatsApp."* — assim, mesmo com RAG fraco, o modelo recebe a instrução no system.
4. **Parâmetros:** `tone_of_voice: friendly` + `message_size: short` ajudam respostas humanas e curtas (§ 10.1).
5. **Orquestrador:** antes de `/ask`, o router pode classificar `saudacao` ou rota fixa para "quem é você" com resposta **template** (sem LLM) — útil se quiser 100% previsível.

**Exemplo real (prod mar/2026):** última troca no Zap — utilizador *"Quem é você ?"* seguido de resposta de fallback *"A assistente não conseguiu responder agora..."* → indica que a API devolveu resposta vazia ou o job terminou sem texto utilizável; aplicar os itens 1–3 acima reduz esse caso.

---

## 5. Contexto de conversa (user_id)

Quando `user_id` é enviado no `/ask`, a API:

1. **Recupera as últimas mensagens** desse usuário naquele projeto (até 10 mensagens, ~6 turnos).
2. **Inclui o histórico no prompt** enviado à LLM, permitindo que o usuário faça perguntas de follow-up naturalmente.
3. **Persiste pergunta e resposta** no histórico para futuras consultas.

**Exemplo de conversa com contexto:**

```
Usuário: "Vocês aceitam cartão?"
Assistente: "Sim, aceitamos cartões de crédito e débito..."

Usuário: "E PIX?"         ← a LLM entende que é sobre formas de pagamento
Assistente: "Sim, também aceitamos PIX. A chave é..."
```

**Recomendação para projetos WhatsApp:** use o número de telefone do usuário (ex.: `5511999990000`) como `user_id`. Isso garante que cada pessoa tenha seu próprio contexto de conversa.

---

## 6. Perfil do usuário (user_profile)

Cada usuário pode ter um **perfil por projeto** com informações pessoais que enriquecem as respostas da LLM.

### 6.1 Criar/atualizar perfil — `PUT /users/profile`

```json
{
  "user_id": "5511999990000",
  "project_id": "bikeanjoall_2026",
  "display_name": "Maria Silva",
  "birth_date": "1990-05-15",
  "notes": "Ciclista frequente, prefere rotas com ciclovia",
  "metadata": {
    "cidade": "São Paulo",
    "bicicleta": "Speed",
    "condicoes_saude": "asmática leve",
    "experiencia": "intermediária"
  }
}
```

**Comportamento do `metadata`:** campos são **mesclados** (merge), não substituídos. Então você pode enviar só os campos novos em atualizações futuras:

```json
{
  "user_id": "5511999990000",
  "project_id": "bikeanjoall_2026",
  "metadata": { "peso_kg": 65 }
}
```

Isso adiciona `peso_kg` sem apagar `cidade`, `bicicleta`, etc.

### 6.2 Consultar perfil — `GET /users/profile/{project_id}/{user_id}`

```bash
curl -s -H "Authorization: Bearer $LLM_API_TOKEN" \
  "$LLM_BASE/users/profile/bikeanjoall_2026/5511999990000" | jq .
```

### 6.3 Como o perfil influencia a LLM

Quando o usuário faz uma pergunta, a LLM recebe no system prompt:

```
About the current user:
- Name: Maria Silva
- Birth date: 1990-05-15 (age: 35)
- Notes: Ciclista frequente, prefere rotas com ciclovia
- cidade: São Paulo
- bicicleta: Speed
- condicoes_saude: asmática leve
- experiencia: intermediária
```

Isso permite respostas personalizadas -- por exemplo, ao recomendar uma rota, a LLM pode considerar que a pessoa é asmática e prefere ciclovias.

### 6.4 Boas práticas por projeto

**BikeAnjoAll_2026** -- sugestão de campos no `metadata`:
- `cidade`, `bairro` -- para recomendações locais
- `experiencia` (iniciante/intermediária/avançada)
- `bicicleta` (tipo)
- `condicoes_saude` -- se o usuário informar voluntariamente
- `objetivos` (lazer, transporte, exercício)

**Projetos de atendimento geral:**
- `plano` ou `tipo_cliente`
- `idioma_preferido`
- `contato_alternativo`

A chave é: **passe as informações que o projeto coletar do usuário na primeira conversa**. Quanto mais contexto, melhores as respostas.

---

## 7. Gestão de conversa (reset e auto-resumo)

### 7.1 Reset manual

Limpa todo o histórico de conversa de um usuário (o perfil é preservado):

```bash
curl -s -X POST "$LLM_BASE/users/conversation/reset" \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "5511999990000", "project_id": "bikeanjoall_2026"}' | jq .
```

Response:
```json
{
  "user_id": "5511999990000",
  "project_id": "bikeanjoall_2026",
  "messages_deleted": 42,
  "message": "Conversation reset. 42 messages deleted. Profile preserved."
}
```

### 7.2 Auto-resumo mensal (automático)

O sistema **automaticamente** a cada 24h:

1. Identifica conversas com mais de 30 dias
2. Agrupa por mês e gera um **resumo compacto** usando a própria LLM
3. Armazena o resumo na tabela `conversation_summary`
4. Deleta as mensagens brutas antigas

**Resultado:** o banco não cresce indefinidamente, mas a LLM ainda "lembra" o contexto geral das conversas anteriores através dos resumos.

O prompt recebe algo como:

```
Summary of past conversations with this user:

[2026-01] (28 messages):
Usuário perguntou sobre rotas de ciclovia em SP, horários do Bike Anjo, e como
registrar uma bicicleta. Demonstrou interesse em participar como voluntário.

[2026-02] (15 messages):
Perguntou sobre eventos de ciclismo, problemas com freios da bike, e pediu
recomendação de oficina no centro de SP.
```

### 7.3 Forçar manutenção manualmente

```bash
curl -s -X POST "$LLM_BASE/users/conversation/maintenance" \
  -H "Authorization: Bearer $LLM_API_TOKEN" | jq .
```

Response:
```json
{
  "users_processed": 5,
  "summaries_created": 3,
  "messages_deleted": 127
}
```

---

## 8. Exemplos de integração por linguagem

### 8.1 Python (httpx) — Recomendado

```python
import os
import time
import httpx

# LLM_API_URL: tailnet (B) ou HTTPS público (A) — ver § 1.1
LLM_BASE = os.environ.get("LLM_API_URL", "http://127.0.0.1:28471")
LLM_TOKEN = os.environ.get("LLM_API_TOKEN", "SEU_TOKEN")
HEADERS = {"Authorization": f"Bearer {LLM_TOKEN}", "Content-Type": "application/json"}

def ask_llm(project_id: str, question: str, user_id: str | None = None, timeout: int = 300) -> dict:
    """Envia pergunta e aguarda resposta (polling síncrono)."""
    payload = {"project_id": project_id, "question": question}
    if user_id:
        payload["user_id"] = user_id

    with httpx.Client(timeout=30.0) as client:
        # 1. Criar job
        r = client.post(f"{LLM_BASE}/ask", json=payload, headers=HEADERS)
        r.raise_for_status()
        job_id = r.json()["job_id"]

        # 2. Poll status
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = client.get(f"{LLM_BASE}/status/{job_id}", headers=HEADERS)
            status = r.json()["status"]
            if status in ("done", "no_answer", "need_more_info", "failed", "cancelled"):
                break
            time.sleep(3)

        # 3. Buscar resultado
        r = client.get(f"{LLM_BASE}/result/{job_id}", headers=HEADERS)
        return r.json()


# Uso
result = ask_llm("bikeanjoall_2026", "Qual o horário?", user_id="5511999990000")
print(result["answer"])
```

### 8.2 Python (httpx async)

```python
import httpx
import asyncio

async def ask_llm_async(project_id: str, question: str, user_id: str | None = None) -> dict:
    payload = {"project_id": project_id, "question": question}
    if user_id:
        payload["user_id"] = user_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{LLM_BASE}/ask", json=payload, headers=HEADERS)
        r.raise_for_status()
        job_id = r.json()["job_id"]

        for _ in range(100):
            r = await client.get(f"{LLM_BASE}/status/{job_id}", headers=HEADERS)
            status = r.json()["status"]
            if status in ("done", "no_answer", "need_more_info", "failed", "cancelled"):
                break
            await asyncio.sleep(3)

        r = await client.get(f"{LLM_BASE}/result/{job_id}", headers=HEADERS)
        return r.json()
```

### 8.3 Node.js / TypeScript

```typescript
// LLM_API_URL — § 1.1 (ex.: process.env.LLM_API_URL ou tailnet)
const LLM_BASE = process.env.LLM_API_URL ?? "http://127.0.0.1:28471";
const LLM_TOKEN = process.env.LLM_API_TOKEN;

async function askLlm(projectId: string, question: string, userId?: string) {
  const headers = {
    "Authorization": `Bearer ${LLM_TOKEN}`,
    "Content-Type": "application/json",
  };

  // 1. Criar job
  const askRes = await fetch(`${LLM_BASE}/ask`, {
    method: "POST",
    headers,
    body: JSON.stringify({ project_id: projectId, question, user_id: userId }),
  });
  const { job_id } = await askRes.json();

  // 2. Poll
  let status = "queued";
  const terminalStatuses = new Set(["done", "no_answer", "need_more_info", "failed", "cancelled"]);
  for (let i = 0; i < 100 && !terminalStatuses.has(status); i++) {
    await new Promise(r => setTimeout(r, 3000));
    const statusRes = await fetch(`${LLM_BASE}/status/${job_id}`, { headers });
    ({ status } = await statusRes.json());
  }

  // 3. Resultado
  const resultRes = await fetch(`${LLM_BASE}/result/${job_id}`, { headers });
  return resultRes.json();
}
```

### 8.4 Bash / curl

```bash
# LLM_API_URL — § 1.1 (exporta LLM_API_URL no ambiente)
LLM_BASE="${LLM_API_URL:-http://127.0.0.1:28471}"

# Perguntar
RESP=$(curl -s -X POST "$LLM_BASE/ask" \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id":"bikeanjoall_2026","question":"O que é o Bike Anjo?","user_id":"5511999990000"}')
JOB_ID=$(echo "$RESP" | jq -r '.job_id')

# Poll (a cada 5s, máximo 60 tentativas = 5 min)
for i in $(seq 1 60); do
  STATUS=$(curl -s -H "Authorization: Bearer $LLM_API_TOKEN" "$LLM_BASE/status/$JOB_ID" | jq -r '.status')
  case "$STATUS" in done|no_answer|need_more_info|failed|cancelled) break ;; esac
  sleep 5
done

# Resultado
curl -s -H "Authorization: Bearer $LLM_API_TOKEN" "$LLM_BASE/result/$JOB_ID" | jq .
```

---

## 9. Como incorporar um projeto na API LLM

Para a API conhecer um projeto e responder perguntas (e o roteador orientar com base em fluxos), você precisa: **(1)** ter o **caminho principal do projeto** no disco; **(2)** dentro dele, **duas pastas** das quais a API se alimenta — **biblioteca de conteúdo** e **mapa de fluxos**; **(3)** registrar o projeto e **disparar a indexação**. Quem dispara é você (ou um script/cron); a API só consome as pastas que você configurou.

### 9.1 Estrutura do projeto: duas pastas obrigatórias

Dentro do caminho principal do projeto, devem existir:

| Pasta | Uso |
|-------|-----|
| **Biblioteca de conteúdo** | Textos, FAQ, documentação que a LLM usa para responder perguntas (RAG). Ex.: `bibliotecaConteudoLLM`, `bibliotecaLLM_webplacecc`, `content`. |
| **Mapa de fluxos** | Fluxos disponíveis, templates, regras de entrada da mensagem. Alimenta o roteador e o contexto da LLM. Ex.: `mapaFluxosLLM`. |

Exemplo de layout:

```
/caminho/principal/do/projeto/
├── bibliotecaConteudoLLM/    ← conteúdo (ou outro nome que você usar)
│   ├── sobre.md
│   ├── faq.md
│   └── ...
└── mapaFluxosLLM/            ← fluxos
    ├── 01_mapa_entrada_mensagem.md
    ├── 03_fluxos_disponiveis.md
    └── templates.json
```

A API **não** recebe “o caminho do projeto” como um único campo. Ela trabalha com **sources**: uma **lista de caminhos** dessas pastas. Ou seja: você informa o caminho da pasta de conteúdo **e** o caminho da pasta de fluxos (cada um como um source).

### 9.2 Como as bibliotecas são consumidas e indexadas

- **Consumo:** a API lê apenas o que está em **sources** (as pastas que você configurou). Cada source é uma pasta no disco; o **ingest** varre essas pastas (recursivamente), lê arquivos **.txt, .md, .markdown, .rst, .json**, e indexa o texto em uma base vetorial (Chroma) **por projeto**.
- **Um único índice por projeto:** conteúdo e mapa de fluxos entram no **mesmo** índice. A LLM (em `/ask`) e o roteador (em `/router`) usam esse índice para responder e sugerir rota.
- **Quem dispara a indexação:** você (ou um script). A API não descobre sozinha os projetos nem reindexa automaticamente.
- **Como disparar:**
  1. **Registrar o projeto** no banco com `project_id` e a lista de pastas (sources) = caminho da biblioteca de conteúdo + caminho do mapa de fluxos.
  2. **Chamar** `POST /ingest` com `project_id` (ou rodar o script de ingest localmente). Isso indexa tudo que está nas pastas configuradas.

Depois do ingest, o projeto passa a aceitar `/ask` e o `/router` (quando usar o índice por projeto) terá contexto dos fluxos.

### 9.3 Passo a passo: incorporar um novo projeto

**Checklist (ordem recomendada):**

0. **Base de dados:** com código actual, aplicar migrações Prisma/SQL em `llm_api/prisma/migrations/` (inclui tabela de chaves por projeto). Ver [04-developer-guide.md](./04-developer-guide.md).
1. **Definir os caminhos** das duas pastas (conteúdo + fluxos). Ex.: `/Users/voce/projects/meuapp/bibliotecaConteudoLLM` e `/Users/voce/projects/meuapp/mapaFluxosLLM`.

2. **No ambiente da llm_api** (onde a API roda), configurar no `.env` a variável de sources do projeto (nome em maiúsculas + `_SOURCES`). Ex. para projeto `meu_projeto`:
   ```bash
   MEU_PROJETO_SOURCES=/caminho/para/meuapp/bibliotecaConteudoLLM,/caminho/para/meuapp/mapaFluxosLLM
   ```
   (Se o projeto tiver seed próprio, ele lê essa variável; caso contrário, use SQL ou script para gravar no banco.)

3. **Registrar no banco:** rodar o seed do projeto (ex.: `python scripts/seed_webplacecc.py`), chamar `POST /projects` (ver § 3.3) ou inserir manualmente na tabela `Project` com `project_id` e `sources` = array com os dois caminhos.

4. **Disparar a indexação:** chamar a API com token:
   ```bash
   curl -X POST "$LLM_BASE/ingest" \
     -H "Authorization: Bearer $LLM_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"project_id": "meu_projeto"}'
   ```
   Ou, no servidor da llm_api:  
   `python -c "import asyncio; from app.ingest.indexer import run_ingest; asyncio.run(run_ingest('meu_projeto'))"`

5. **Pronto:** o projeto aceita `POST /ask` e `POST /router` (com `project_id`) usando o conhecimento indexado.

6. **(Opcional) Chave por projeto:** no **Dashboard → Projetos → [slug] → Chaves API**, gerar uma chave e configurar o cliente com `Authorization: Bearer itcs_...` em vez do token global (ver § 2 e [03-api-reintegration.md](./03-api-reintegration.md)).

7. **(Opcional) Bibliotecas partilhadas:** no `config_json` do projeto, `shared_libraries: ["slug-outro-indice"]` — ver [03-api-reintegration.md](./03-api-reintegration.md) §5.

### 9.4 Ingest: criar projeto se não existir

O `POST /ingest` **cria o projeto automaticamente** se ele não existir no banco, desde que as pastas de índice estejam definidas. Duas formas:

1. **Body com `sources`:** envie `{"project_id": "meu_projeto", "sources": ["/caminho/biblioteca", "/caminho/fluxos"]}` — a API cria o projeto e roda o ingest.
2. **Variável de ambiente:** configure `MEU_PROJETO_SOURCES=/caminho/biblioteca,/caminho/fluxos` no `.env` da llm_api — ao chamar ingest sem o projeto existir, a API usa essa variável, cria o projeto e indexa.

Se o projeto não existir e não houver `sources` no body nem variável de ambiente, a API retorna 400.

### 9.5 Como o projeto dispara o ingest quando tiver dados novos

Faz parte da incorporação: **quem dispara a indexação** quando o projeto ganha conteúdo novo ou atualiza o mapa de fluxos é o **próprio projeto** (ou o orquestrador que o gerencia). A API não reindexa sozinha.

**Opções para o projeto disparar o ingest:**

1. **Chamar a API** (recomendado quando o projeto tem acesso à URL da API e ao token):
   ```bash
   curl -X POST "$LLM_API_URL/ingest" \
     -H "Authorization: Bearer $LLM_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"project_id": "webplacecc"}'
   ```
   O projeto pode rodar esse `curl` (ou equivalente em Node/Python) após:
   - um deploy que alterou arquivos na biblioteca ou no mapa de fluxos;
   - um job/cron que atualiza conteúdo;
   - uma ação manual de “reindexar” no painel do projeto.

2. **Script no servidor da API:** se o projeto não tiver como chamar a API (ex.: está em outra rede), alguém com acesso ao servidor onde a llm_api roda pode executar:
   ```bash
   cd /caminho/para/llm_api
   source .env && .venv/bin/python -c "import asyncio; from app.ingest.indexer import run_ingest; asyncio.run(run_ingest('webplacecc'))"
   ```

3. **Automação (cron, CI):** agendar a chamada `POST /ingest` ou o script acima (ex.: após sync do repositório do projeto que contém biblioteca e mapa de fluxos).

**Boas práticas:** após qualquer alteração em arquivos da biblioteca de conteúdo ou do mapa de fluxos, disparar o ingest (com `project_id` do projeto). Sem novo ingest, a LLM e o roteador continuam usando o índice antigo.

### 9.6 Registrar sem seed (SQL direto)

Se não houver script de seed para o projeto, insira no banco:

```sql
INSERT INTO "Project" (id, project_id, name, sources, config_json, created_at, updated_at)
VALUES (
  gen_random_uuid()::text,
  'meu_projeto',
  'Meu Projeto',
  ARRAY['/caminho/para/biblioteca_conteudo', '/caminho/para/mapa_fluxos'],
  '{"chunking":{"chunk_size":512,"chunk_overlap":64,"separator":"\\n\\n"},"embedding_model":"mxbai-embed-large","policies":{"prefer_cite_sources":true,"when_no_answer":"no_answer","max_chunks_to_retrieve":5}}',
  NOW(), NOW()
);
```

Em seguida, chame `POST /ingest` como acima.

### 9.7 Exemplo: projeto webplacecc

No `.env` da llm_api, defina **WEBPLACECC_SOURCES** com as duas pastas (caminho principal do projeto + subpastas de conteúdo e fluxos):

```bash
WEBPLACECC_SOURCES=/caminho/para/webplacecc/bibliotecaLLM_webplacecc,/caminho/para/webplacecc/mapaFluxosLLM
```

Depois: rodar o seed (atualiza os sources no banco) e disparar o ingest:

```bash
.venv/bin/python scripts/seed_webplacecc.py
.venv/bin/python -c "import asyncio; from app.ingest.indexer import run_ingest; asyncio.run(run_ingest('webplacecc'))"
```

Ou, após o seed, chamar `POST /ingest` com `project_id: "webplacecc"` pela API.

### 9.8 Boas práticas para bibliotecas

- **Texto limpo:** remova headers HTML, menus, footers. Quanto mais limpo, melhor o RAG.
- **Arquivos pequenos e focados:** prefira um arquivo por tema (ex.: `faq.md`, `horarios.md`) a um arquivo gigante.
- **Nomeie bem os arquivos:** o path aparece como `source` na resposta e ajuda a LLM a citar.
- **Reindexe após mudanças:** após adicionar ou editar conteúdo, chame `POST /ingest`.

---

## 10. Guia de Parametrização Avançada e Qualidade

A qualidade de cada **request** (chamado) e da resposta final depende da calibração fina do projeto. Além das regras automáticas descritas em [07-llm-calibration.md](./07-llm-calibration.md), você pode configurar comportamentos específicos no `config_json` do projeto.

### 10.1 Calibração de Texto (Tom e Tamanho)

Configure o tom de voz e o tamanho das mensagens no objeto `llm_options`:

```json
"llm_options": {
  "tone_of_voice": "sales",   // informal | friendly | technical | sales | direct
  "message_size": "short",    // short | medium | detailed
  "temperature": 0.3
}
```

| Parâmetro | Valores | Descrição |
|-----------|---------|-----------|
| `tone_of_voice` | `direct` (default) | Respostas objetivas e sem rodeios. |
| | `friendly` | Tom acolhedor e prestativo. |
| | `informal` | Tom descontraído e amigável. |
| | `technical` | Tom preciso e profissional. |
| | `sales` | Focado em converter o interesse em serviço/contato. |
| `message_size` | `short` | Máximo 2 parágrafos. |
| | `medium` (default) | 2 a 4 parágrafos. |
| | `detailed` | Explicações completas baseadas no contexto. |

### 10.2 Busca Profunda (Search Depth)

Se o projeto lida com consultas complexas ou manuais densos, use o `search_depth` em `policies`:

```json
"policies": {
  "search_depth": "deep",
  "max_chunk_distance": 1.0,
  "max_chunks_to_retrieve": 5
}
```

- **`standard` (default):** busca normal no índice.
- **`deep`:** se a busca inicial for insuficiente ou se configurado, a API realiza uma segunda busca mais permissiva (maior `top_k` e maior distância) para tentar encontrar interrelações na biblioteca antes de desistir. Útil para "assuntos insistidos" pelo usuário.

### 10.3 Otimização da Biblioteca (Conteúdo Fonte)

A qualidade da resposta é diretamente proporcional à estrutura dos seus arquivos `.md`.

1. **Use Headings (##, ###):** O sistema quebra o texto por seções. Seções bem definidas geram chunks mais coesos.
2. **Metadados "Sobre:":** Comece seus arquivos com `Sobre: [Título do Tema]`. Isso ajuda o ranking do RAG.
3. **Parágrafos curtos:** Evite blocos de texto gigantes (>800 caracteres).
4. **Interrelações:** Se um documento A cita o assunto B, garanta que o documento B também exista e use termos similares.

**Dica:** Use a ferramenta interna `optimize_library.py` (no servidor) para analisar seus arquivos e receber sugestões de melhoria.

### 10.4 Resumo de Parametrização Sugerida

| Tipo de Projeto | tone_of_voice | message_size | search_depth | max_chunk_distance |
|-----------------|---------------|--------------|--------------|--------------------|
| **Vendas/Leads** | `sales` | `short` | `standard` | `0.8` |
| **Suporte/FAQ** | `friendly` | `medium` | `standard` | `1.0` |
| **Documentação** | `technical` | `detailed` | `deep` | `1.1` |

### 10.5 Instruções Customizadas (System Prompt)

Para ajustes finos que nenhum parâmetro resolve:
- **Arquivo no projeto:** Crie `instrucoes-llm.md` na pasta do projeto e configure `"behavior_instruction_path": "instrucoes-llm.md"` no banco.
- **Uso:** Defina personas (ex: "Você é um especialista jurídico") ou proibições específicas do seu negócio.

---

## 11. Rede e segurança

- A API **nunca** é exposta à internet — apenas via Tailscale (entre suas máquinas).
- Use **ACLs do Tailscale** para restringir quais nós podem acessar o serviço.
- O token deve ser forte (hex 24+ bytes) e **diferente** entre ambientes se necessário.
- Logs não gravam conteúdo de perguntas/respostas por padrão.

---

## 12. Troubleshooting

| Problema | Solução |
|----------|---------|
| `401 Unauthorized` | Token em falta ou inválido: confere `LLM_API_TOKEN` (global) **ou** chave por projeto (Dashboard); header `Authorization: Bearer ...` |
| `403` com chave por projeto | `project_id` no corpo não coincide com o projecto da chave — alinhar ou omitir conforme contrato em § 2 |
| `404 project not found` | Projeto não registrado no banco — rode o seed ou insira via SQL |
| `status: failed` no job | Verifique logs da API; Ollama pode estar fora do ar (`/health`) |
| Respostas lentas (>2min) | Normal para 7B model; aumente timeout do polling |
| Respostas genéricas | Reindexe (`/ingest`); verifique se os textos fonte são relevantes |
| Respostas com frases meta ou autodesvalorizantes ("Com base no contexto...", "não encontrei informação") | Ver [07-llm-calibration.md](./07-llm-calibration.md); reforçar instruções no projeto (`instrucoes-llm.md`) e conferir prompt base |
| "Quem é você?" / perguntas existenciais → resposta má ou fallback humano no Zap | RAG sem chunk relevante ou resposta vazia da API; ver **§ 4.5** — ficheiro `identidade-assistente.md` + regra em `instrucoes-llm.md` + reforço no `system_prompt` do cliente; reindexar |
| Orquestrador mostra "assistente não conseguiu responder" com tag LLM ativa | `GET /result` sem `answer` ou string vazia; ver logs do job (`GET /jobs`), `/health` (Ollama), timeout; conferir se `question` chega corretamente e se histórico não confunde o modelo |
| `connection refused` | **llm_server** offline, API parada, ou Tailscale desconectado |
| `timeout` (servidor → **llm_server**) | VM em cloud atrás de DERP sem TCP estável: ver túnel em [refs/operacao-tailscale.md](./refs/operacao-tailscale.md) secção 6, ou proxy nginx opcional (secção 6.2) — IPs reais em `local-only/` |
| `/extract` retorna sempre `null` | Step inválido ou resposta da LLM fora do formato; ver § 3.1. Confira se Ollama está no ar (`/health`) |

---

## 13. Novos projetos: instalação, bibliotecas e mapa de fluxos

**Manual de instalação/integração:** este documento. Para um novo projeto usar a LLM: (1) obter `LLM_API_TOKEN` e escolher URL base **caminho A ou B** (§ 1.1 e § 2); (2) registrar o projeto no banco (seed ou API); (3) configurar biblioteca de conteúdo (pastas/arquivos do projeto, ingest § 4); (4) chamar `/ask` (e opcionalmente perfil, conversa) conforme § 4–7.

**Extração de NF (itcsNFextract):** `POST /nfExtract` na mesma API — manual em [ManualNF_Extract](./refs/ManualNF_Extract) (mesmas duas URL bases).

**Mapa de fluxos:** para o roteador (e a LLM) conhecerem os fluxos do projeto, inclua a pasta do mapa (ex.: `mapaFluxosLLM/`) nos **sources** do projeto e rode o **ingest** (ver § 9). Não há mecanismo separado: a mesma indexação que alimenta o `/ask` passa a incluir os .md (e .json) do mapa; quando o roteador usar o índice por projeto, terá esse contexto. Referência: webplacecc com `bibliotecaLLM_webplacecc` + `mapaFluxosLLM` em WEBPLACECC_SOURCES. O roteador só orienta; a decisão final é do orquestrador.

**estudosmobi — fluxosLLM:** no projeto estudiosmobi a pasta `fluxosLLM/` está nos sources (junto com `bibliotecaConteudoLLM/`). Use-a para: (1) MDs com o que foi discutido e como incorporar na LLM; (2) dados para melhorar o roteador; (3) tom de resposta. O arquivo `instrucoes-llm.md` dentro de `fluxosLLM` é lido pela API e injetado no system prompt (comportamento/tom). Os demais .md são indexados e podem ser recuperados como contexto. Após editar, rode o ingest do projeto.

**Roteador — contexto:** o endpoint aceita mensagem e contexto opcional: `project_id`, nome do usuário, fluxo/etapa atual, últimas N mensagens (ex.: 3). O orquestrador envia o que achar relevante; nada é obrigatório além da mensagem.

**Pergunta livre (sem project_id):** consulta à LLM sem projeto. **Não pode expor dados de projetos.** Por enquanto a resposta é placeholder (ex.: “frase do dia” ou texto que indique que a requisição chegou na LLM). Futuramente haverá algum tipo de biblioteca para essas perguntas livres.

**Modelos de consulta/fluxo:** este manual é a única referência de integração. Quando a complexidade dos fluxos crescer, pode existir a pasta **modelosConsultaLLM/** (ou equivalente) com modelos de consulta, fluxo, etc.; o manual continuará como entrada única e indicará o caminho para essa pasta.

---

## 14. Operação: últimas mensagens do Zap (Postgres)

As mensagens do WhatsApp (zapzap) ficam na tabela `zapzap_messages` no **mesmo** Postgres do sistemaBA (schema partilhado). Útil para debug sem abrir o dashboard.

**No servidor de produção** (com `DATABASE_URL` carregado de `.env.prod` do sistemaBA):

```bash
cd /var/www/bikeanjo2026all/sistemaBA && set -a && . ./.env.prod && set +a && node -e "
const { Client } = require('pg');
const c = new Client({ connectionString: process.env.DATABASE_URL });
c.connect()
  .then(() => c.query(\`
    SELECT id, direction, phone,
           LEFT(COALESCE(text,''), 400) AS text_preview,
           sent_at
    FROM zapzap_messages
    ORDER BY sent_at DESC
    LIMIT 10
  \`))
  .then(r => { console.log(JSON.stringify(r.rows, null, 2)); return c.end(); });
"
```

Substitua `LIMIT 10` por `3` se quiser só as três últimas. `direction`: `in` = utilizador, `out` = bot/atendente.

---

**Anterior:** [01-overview.md](./01-overview.md) · **Seguinte:** [03-api-reintegration.md](./03-api-reintegration.md)
