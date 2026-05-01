# Planejamento: LLM local 24/7 no Mac mini (M4, 32GB) + API FastAPI + Tailscale

**Objetivo:** Motor de inferência local com RAG multi-projeto, API assíncrona, acesso seguro via Tailscale, sem expor porta pública.

---

## Resumo das decisões principais (10 linhas)

1. **Motor:** Ollama (inferência local, boa integração Apple Silicon, modelos quantizados).
2. **API:** FastAPI em localhost em **porta atípica 28471** (evita conflito com outros projetos); só Tailscale publica o serviço; sem bind em 0.0.0.0.
3. **RAG:** Embeddings via modelo leve (e.g. nomic-embed ou similar); índice vetorial em Chroma/sqlite-vss em arquivo por projeto; chunking configurável por projeto.
4. **Armazenamento:** **PostgreSQL** (schema e migrações via **Prisma**) para registry de projetos, jobs, fila de chamados e temáticas de bibliotecas; pastas em disco para documentos fonte; índices vetoriais por projeto em `data/<project_id>/`.
5. **Fila:** Fila de jobs persistida no PostgreSQL (status queued/working/done/…); workers (1–2 concorrentes) consomem da fila; polling em `/status` e `/result`.
6. **Multi-projeto:** Project Registry no Postgres (Prisma) com `project_id`, paths, chunking, embedding model, políticas e **temáticas** (tags/tópicos da biblioteca); roteamento por `project_id` obrigatório na API; auto-router opcional por temáticas/palavras-chave quando `project_id` ausente.
7. **Segurança:** API com header `Authorization: Bearer <token>`; Tailscale ACL para limitar quem acessa o node; nenhuma porta aberta na internet.
8. **Modelos:** 1x 7B para chat (ex.: Llama 3.2 8B ou Mistral 7B Q4); 1x embeddings leve; parâmetros conservadores (temp baixa, top_k limitado) e política “responder só com base em trechos; senão no_answer/need_more_info”.
9. **Deploy:** launchd (serviço de usuário) para FastAPI + workers; `caffeinate` ou Preferências “Impedir que o computador durma”; rotação de logs com logrotate ou equivalente macOS.
10. **Observabilidade:** Logs estruturados (JSON) para stdout; métricas simples (contagem de jobs, latência, erros) em `/metrics` (formato texto ou Prometheus); health em `/health`.

---

## 1. Arquitetura

### 1.1 Componentes

| Componente | Tecnologia / abordagem | Função |
|------------|------------------------|--------|
| Motor de inferência | Ollama | Rodar modelo 7B quantizado e modelo de embeddings localmente |
| API | FastAPI | Endpoints REST, auth por token, binding em localhost |
| RAG | Embeddings (Ollama ou sentence-transformers) + índice vetorial | Busca por similaridade em “bibliotecas” por projeto |
| Armazenamento | PostgreSQL (Prisma) + filesystem | Registry de projetos, jobs, temáticas; docs e índices em disco |
| Fila de jobs | PostgreSQL (tabela Jobs com status) + workers | Workers (1–2) consomem jobs em status queued; persistência e histórico no Postgres |
| Observabilidade | Logs JSON + endpoint `/metrics` | Debug e métricas básicas |
| Acesso remoto | Tailscale (subnet/router ou serve) | API acessível só na rede Tailscale, sem porta pública |

### 1.2 Fluxo alto nível

- Cliente (na rede Tailscale) chama `https://<tailscale-host>:28471/ask` com `project_id` e pergunta.
- API valida token, cria job, coloca na fila, retorna `job_id` e mensagem “recebido”.
- Worker pega o job, carrega config do projeto, busca RAG na biblioteca do projeto, chama Ollama com contexto, persiste resultado.
- Cliente faz polling em `/status/{job_id}` e depois `/result/{job_id}`.

### 1.3 Segurança

- API escuta só em `127.0.0.1:28471` (porta atípica para não conflitar com outros projetos).
- Tailscale “serve” ou “expose” apenas a porta 28471 para a rede Tailscale; ACL restringe nós permitidos.
- Todos os endpoints (exceto `/health` se desejado) exigem `Authorization: Bearer <TOKEN>`; token configurável por env ou arquivo.

---

## 2. Multi-projeto e Project Registry

### 2.1 Modelo do Project Registry

Cada projeto é um registro com:

- **project_id** (string, único): identificador usado na API.
- **name** (opcional): nome legível.
- **sources**: lista de caminhos locais (pastas) para indexar; em geral as bibliotecas ficam **dentro das pastas de cada projeto** (ex.: `.../bikeanjoall_2026/content`).
- **chunking**: `chunk_size`, `chunk_overlap`, `separator` (ex.: `\n\n`).
- **embedding_model**: nome do modelo de embeddings (ex.: `nomic-embed-text`).
- **index_backend**: ex. `sqlite_vss` ou `chroma` (path do índice em `data/<project_id>/`).
- **policies**:
  - `prefer_cite_sources`: boolean (sempre que possível citar trechos).
  - `when_no_answer`: `no_answer` | `need_more_info` (o que retornar se confiança baixa).
  - `max_chunks_to_retrieve`: int (ex.: 5).
- **temáticas (opcional):** lista de tags/tópicos da biblioteca (ex.: `["infra", "dns", "tailscale"]`) para auto-router e organização.

Armazenamento (PostgreSQL via Prisma):

- **Tabelas:** `Project` (project_id, name, config_json, paths, chunking, embedding_model, policies, created_at, updated_at), `ProjectTheme` (project_id, theme) para temáticas, `Job` (id, project_id, status, question_hash, result, sources, created_at, …).
- **Config opcional por arquivo:** `llm_api/projects/<project_id>/config.json` sobrescreve ou complementa (paths, chunking, policies).

### 2.2 Isolamento

- Cada consulta (`/ask`) recebe `project_id`. O worker carrega apenas o índice e documentos daquele projeto.
- Nenhum dado de outro projeto é usado na resposta, a menos que exista um “projeto composto” explicitamente configurado (ex.: projeto que inclui outras bibliotecas por referência) — fora do MVP.

### 2.3 Roteamento da biblioteca

- **Com project_id:** API usa diretamente o registry para esse `project_id` e dispara o job com essa biblioteca.
- **Sem project_id (auto-router opcional):** 
  - Classificador por regras: **temáticas** (ProjectTheme) e/ou palavras-chave por projeto; primeira pergunta ou campo `hint` é comparado às regras; escolhe o projeto com melhor match.
  - Se não houver match, retornar 400 pedindo `project_id` ou criar job com “projeto default” se configurado.

---

## 3. Endpoints e contrato

### 3.1 Autenticação

- Header: `Authorization: Bearer <API_TOKEN>`.
- Token em variável de ambiente `LLM_API_TOKEN` ou arquivo (não versionado).

### 3.2 Endpoints

| Método | Path | Descrição |
|--------|------|-----------|
| POST | `/ingest` | Indexar/reindexar um projeto (body: `project_id`, opcional `incremental`) |
| POST | `/ask` | Criar job de pergunta (body: `project_id`, `question`, opcional `hint` para auto-router) |
| GET | `/status/{job_id}` | Estado do job e progresso |
| GET | `/result/{job_id}` | Resposta final + fontes (após done) |
| GET | `/health` | Liveness (opcional: checar Ollama) |
| GET | `/metrics` | Métricas simples (text/plain ou Prometheus) |

### 3.3 Exemplos de request/response

**POST /ingest**

```json
// Request
{
  "project_id": "itcs",
  "incremental": true
}

// Response 200
{
  "project_id": "itcs",
  "status": "started",
  "message": "Ingest job queued"
}
```

**POST /ask**

```json
// Request
{
  "project_id": "itcs",
  "question": "Como configuro o Tailscale no servidor?"
}

// Response 202
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Question received. Poll /status/{job_id} for progress, then /result/{job_id} for answer.",
  "status_url": "/status/550e8400-e29b-41d4-a716-446655440000",
  "result_url": "/result/550e8400-e29b-41d4-a716-446655440000"
}
```

**GET /status/{job_id}**

```json
// Response 200 (working)
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "working",
  "progress": "retrieving_context",
  "created_at": "2025-03-06T10:00:00Z"
}

// Response 200 (done)
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "done",
  "progress": "complete"
}
```

Valores de `status`: `queued` | `working` | `done` | `no_answer` | `need_more_info` | `failed` | `cancelled`.

**GET /result/{job_id}**

```json
// Response 200
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "done",
  "answer": "Para configurar o Tailscale no servidor...",
  "sources": [
    {
      "id": "doc_abc_chunk_3",
      "path": "docs/cloudflare-dns.md",
      "snippet": "...trecho relevante..."
    }
  ],
  "confidence": "high"
}
```

Para `no_answer` ou `need_more_info`, `answer` pode ser uma mensagem padrão e `sources` vazio ou com sugestões.

---

## 4. Gestão de demanda e UX

- **Ack imediato:** `/ask` retorna 202 com `job_id` e mensagem clara; cliente não fica esperando a resposta na mesma requisição.
- **Timeouts:** 
  - Cliente: timeout de polling alto (ex.: 5 min) ou long polling se implementar depois.
  - Servidor: job com timeout máximo (ex.: 5 min); após isso status `failed`.
- **Retries:** Cliente pode retentar apenas em erros 5xx ou rede; para 4xx (ex.: token inválido) não retentar sem corrigir.
- **Cancelamento:** `DELETE /job/{job_id}` ou `POST /job/{job_id}/cancel` para marcar como `cancelled` e worker desiste ao ver o flag.
- **Deduplicação:** Hash da dupla `(project_id, question_normalized)`; se já existir job recente (ex.: últimos 10 min) com mesmo hash, retornar o `job_id` existente em vez de criar novo (evita fila duplicada).
- **Rate limit:** Leve por `project_id` ou por token (ex.: N requests/minuto por projeto); resposta 429 com `Retry-After`.

---

## 5. Modelos e parâmetros

### 5.1 Modelos sugeridos (Apple Silicon M4, 32GB)

- **Chat (7B quantizado):** 
  - Opção 1: `llama3.2:8b-instruct-q4_0` (Ollama) — boa qualidade e desempenho.
  - Opção 2: `mistral:7b-instruct-q4_0` — alternativa estável.
- **Embeddings (leve):** 
  - `nomic-embed-text` (Ollama) ou `all-minilm` se usar sentence-transformers; priorizar um só para simplicidade.

### 5.2 Parâmetros padrão (estabilidade, anti-alucinação)

- **context size:** 4096 ou 8192 (conforme modelo).
- **temperature:** 0.2–0.3.
- **top_k:** 40–50.
- **top_p:** 0.9.
- Instrução no system prompt: responder apenas com base nos trechos fornecidos; se não houver trecho suficiente, responder “Não encontrei base suficiente” ou “Preciso de mais detalhes sobre X”.

### 5.3 Política anti-alucinação

- Sempre injetar no prompt os trechos recuperados pelo RAG.
- Se score de similaridade médio dos chunks for abaixo de um limiar, ou nenhum chunk retornado, não chamar o LLM para inventar; retornar `no_answer` ou `need_more_info` conforme política do projeto.

---

## 6. Deploy “sempre ligado” no macOS

- **Serviço:** launchd (usuário): `~/Library/LaunchAgents/com.itcs.llmapi.plist` para iniciar o processo da API (ex.: `uvicorn` ou script que sobe FastAPI + workers). Manter um único processo “orquestrador” que sobe API e workers no mesmo processo ou em subprocessos controlados.
- **Não dormir:** 
  - Preferências do Sistema > Energia > Impedir que o computador durma quando o display está desligado; ou
  - `caffeinate -s` em sessão de terminal dedicada (menos ideal que Preferências).
- **Logs:** 
  - stdout/stderr do processo redirecionados para arquivo (ex.: `logs/llmapi.log`); 
  - Rotação com `logrotate` (se instalado) ou script que rotaciona por tamanho/data; ou usar `logging.handlers.RotatingFileHandler` em Python.
- **Índice:** 
  - Reindexação incremental via `/ingest`; em atualização “segura”, escrever índice em diretório temporário e depois swap atômico para o path em uso.

---

## 7. Entregáveis

### 7.1 Lista de tarefas em ordem

**MVP (1 dia)**

- [ ] Ambiente Python (venv), FastAPI, dependências (ollama client, Prisma Client Python ou asyncpg, lib de embeddings/vector store leve).
- [ ] PostgreSQL local (ou Docker): banco criado; Prisma schema com `Project`, `ProjectTheme`, `Job`; migrações aplicadas.
- [ ] Config estática de 1 projeto de teste (project_id, path, chunking, temáticas opcionais).
- [ ] Pipeline de ingestão mínima: listar arquivos, chunk, embed, gravar índice (um backend simples, ex.: Chroma ou sqlite-vss).
- [ ] Endpoint POST `/ask`: criar job, enfileirar, retornar job_id (worker único, síncrono no mesmo processo para MVP).
- [ ] Worker: pegar pergunta, RAG no índice do projeto, chamar Ollama, salvar resposta em `jobs`; marcar status done/no_answer.
- [ ] GET `/status/{job_id}` e GET `/result/{job_id}`.
- [ ] API em localhost na porta **28471**; auth por token no header.
- [ ] Documentar como expor via Tailscale (serve na porta 28471). Ver `../docs/refs/operacao-tailscale.md`.

**Melhorias (1 semana)**

- [ ] POST `/ingest` com suporte incremental e fila de ingest.
- [ ] Fila de jobs no Postgres com limite de workers (ex.: 2) e estados claros (queued/working/done/failed/cancelled).
- [ ] Project Registry completo no Postgres (CRUD ou config por arquivo), temáticas (ProjectTheme) e roteamento por project_id em todos os endpoints.
- [ ] Auto-router opcional (temáticas e palavras-chave).
- [ ] Deduplicação de perguntas (hash + janela de tempo).
- [ ] Timeout e cancelamento de job.
- [ ] Rate limit por project_id.
- [ ] `/health` e `/metrics`; logs estruturados (JSON).
- [ ] launchd plist e rotação de logs; instruções para “não dormir”.
- [ ] Políticas por projeto (no_answer vs need_more_info) e anti-alucinação (limiar de confiança).

### 7.2 Estrutura de pastas do repositório

```
ai2tcs/
├── docs/                          # docs numerados 01–10 + refs/ (nginx, Tailscale, NF Extract)
├── features/                      # serviços satélite (ex.: ExtratNFdata)
├── llm_api/
│   ├── 00_PLANEJAMENTO_LLM_LOCAL.md   # este doc
│   ├── README.md
│   ├── requirements.txt
│   ├── .env.example                   # LLM_API_TOKEN, DATABASE_URL, API_PORT=28471, paths
│   ├── prisma/
│   │   ├── schema.prisma              # Project, ProjectTheme, Job
│   │   └── migrations/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app, porta 28471
│   │   ├── config.py
│   │   ├── auth.py
│   │   ├── db.py
│   │   ├── registry.py
│   │   ├── ingest/ …
│   │   ├── rag/ …
│   │   ├── jobs/ …
│   │   ├── api/ …
│   │   └── models.py
│   ├── data/                          # não versionado (ex.: chroma por projeto)
│   ├── scripts/
│   └── …
└── …
```

### 7.3 Riscos e mitigação

| Risco | Mitigação |
|-------|------------|
| Mac sobrecarregado (CPU/GPU 100%) | Limite de workers (1–2); fila; opcional nice/prioridade do processo; monitorar em `/metrics`. |
| Índice muito grande (disco/RAM) | Chunking maior, menos overlap; índice por projeto; reindexação incremental; limpar projetos não usados. |
| Respostas lentas (>5 min) | Timeout no job; mensagem clara no ack; cliente com polling e timeout próprio. |
| Privacidade (dados nos prompts) | Tudo local (Ollama + dados em disco); API só na Tailscale; token forte; logs sem conteúdo de perguntas/respostas em produção se desejado. |
| Ollama indisponível | `/health` verifica Ollama; retornar 503 e status `failed` no job; alerta ou log para reiniciar Ollama. |

---

## Próximos passos (5 ações iniciais no Mac)

1. **Instalar Ollama e puxar modelos**
   ```bash
   brew install ollama
   ollama serve   # ou rodar como serviço
   ollama pull llama3.2:8b-instruct-q4_0
   ollama pull nomic-embed-text
   ```

2. **Criar venv e dependências em `llm_api/`**
   ```bash
   cd /caminho/para/ai2tcs/llm_api
   python3 -m venv .venv
   source .venv/bin/activate
   pip install fastapi uvicorn ollama sqlite-vss chromadb httpx pydantic-settings
   pip freeze > requirements.txt
   ```

3. **PostgreSQL e Prisma**
   ```bash
   # PostgreSQL local (brew install postgresql@16) ou Docker
   createdb llmapi   # ou via Docker
   cp .env.example .env
   echo "LLM_API_TOKEN=$(openssl rand -hex 24)" >> .env
   echo "DATABASE_URL=postgresql://user:pass@localhost:5432/llmapi" >> .env
   echo "API_PORT=28471" >> .env
   # Prisma: npx prisma init && editar prisma/schema.prisma; npx prisma migrate dev
   ```

4. **Subir API em localhost (porta 28471) e testar health**
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 28471
   curl -H "Authorization: Bearer $LLM_API_TOKEN" http://127.0.0.1:28471/health
   ```

5. **Habilitar Tailscale e expor a porta 28471**
   ```bash
   tailscale set --advertise-exit-node=false  # se não for exit node
   # No admin Tailscale: aprovar “Serve” para a porta 28471 (TCP) neste dispositivo.
   tailscale serve status  # verificar
   ```
   Detalhes para servidores e scripts: ver `../docs/refs/operacao-tailscale.md`.

Depois disso: implementar MVP (schema DB, 1 projeto, ingestão mínima, `/ask` + worker, `/status` e `/result`) conforme checklist do MVP acima.
