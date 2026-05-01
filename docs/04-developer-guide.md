# 04 — Guia do desenvolvedor

Código: `llm_api/`. Integração HTTP (clientes): [02-api-integration.md](./02-api-integration.md). Este ficheiro: setup, testes, extensão da API.

---

## Índice

1. [Setup de desenvolvimento](#setup-desenvolvimento)
2. [Arquitetura](#arquitetura)
3. [Padrões de código](#padrões-código)
4. [Adicionar endpoints](#adicionar-endpoints)
5. [Estender RAG](#estender-rag)
6. [Calibração e desvios da LLM](#calibração-e-desvios-da-llm)
7. [Testes](#testes)
8. [Troubleshooting](#troubleshooting)

---

## Setup de Desenvolvimento

### Pré-requisitos
- Python 3.11+
- PostgreSQL 16+
- Ollama com modelo `llama3:8b` rodando
- Virtualenv

### Instalação Local

```bash
# Clone o repositório GitHub ai2tcs e entre na pasta da API
git clone git@github.com:ianthomaz/ai2tcs.git
cd ai2tcs/llm_api

# Criar virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Banco: use o script de migração (consolidada) ou psql no SQL em prisma/migrations/20250307000000_consolidated/
export DATABASE_URL="postgresql://user:password@localhost:5432/llmapi"
# Ver ../llm_api/README.md e ./02-api-integration.md (pasta docs/) para setup completo.

# Seed (cria projetos de exemplo)
python scripts/seed_bikeanjoall.py

# Migrações Prisma (obrigatório após pull com novas pastas prisma/migrations/)
# Ex.: chaves por projeto + model_alias em jobs — abril/2026
npx prisma migrate deploy

# Rodar server
uvicorn app.main:app --host 127.0.0.1 --port 28471 --reload
```

**Fleet de modelos (env):** além de `OLLAMA_FAST_MODEL` e `OLLAMA_SMART_MODEL`, o código reconhece `OLLAMA_COMPACT_MODEL` e `OLLAMA_REASONER_MODEL` (aliases `compact` e `reasoner` em `get_model_name`). Ver `.env.example`.

**Verificar instalação:**
```bash
curl -H "Authorization: Bearer $LLM_API_TOKEN" http://127.0.0.1:28471/health | jq .
```

Esperado: `{"status":"ok","checks":{"ollama":...,"postgres":...}}`

**Dashboard (Google OAuth):** credenciais só no `.env` (nunca no Git). Preenche `DASHBOARD_GOOGLE_*`, `DASHBOARD_OAUTH_REDIRECT_BASE` e **`DASHBOARD_ALLOWED_EMAILS`** (mínimo um e-mail em minúsculas); alinha URIs no GCP com [refs/cloudflare-edge.md](./refs/cloudflare-edge.md).

---

## Arquitetura

Documentação de contratos e integração: pasta **`docs/`** na raiz do clone ([01-overview.md](./01-overview.md)), irmã de **`llm_api/`** (código da API).

### Estrutura de Diretórios

```
llm_api/
├── app/                          # Código principal
│   ├── main.py                   # FastAPI app e rotas
│   ├── config.py                 # Configurações globais
│   ├── db.py                     # Funções banco de dados
│   ├── registry.py               # Registry de projetos
│   │
│   ├── api/                      # Endpoints
│   │   ├── ask.py                # /ask (pergunta assíncrona)
│   │   ├── extract.py            # /extract (extração síncrona)
│   │   ├── message_router.py      # /router (roteador de mensagens)
│   │   ├── projects.py           # /projects (CRUD)
│   │   ├── jobs.py               # /jobs, /stats
│   │   ├── users.py              # /users/profile, /conversation
│   │   └── health.py             # /health, /metrics
│   │
│   ├── rag/                      # RAG (Retrieval-Augmented Generation)
│   │   ├── retrieve.py           # Busca de chunks (Chroma)
│   │   └── prompt.py             # Construção de prompts
│   │
│   ├── ingest/                   # Indexação
│   │   ├── indexer.py            # Coordena ingest
│   │   └── embeddings.py         # Chamadas a Ollama
│   │
│   └── jobs/                     # Background jobs
│       ├── worker.py             # Processing de jobs (RAG+LLM)
│       └── conversation_maintenance.py # Auto-resumo
│
├── prisma/                       # ORM + migrations
│   ├── schema.prisma             # Schema do banco
│   └── migrations/               # Histórico de migrations
│
├── scripts/                      # Utilitários
│   ├── seed_bikeanjoall_2026.py  # Setup projeto
│   └── setup.sh                  # Setup inicial
│
├── tests/                        # Testes unitários
├── requirements.txt              # Dependências
├── .env.example                  # Variáveis de ambiente
└── UPGRADES.md                   # Roadmap de melhorias
```

### Workers por alias de modelo (Abril 2026)

No arranque (`app/main.py` lifespan), a API pode lançar **várias corrotinas** `job_worker._worker_coro(alias_filter=...)`, uma por alias (`fast`, `compact`, `smart`, `reasoner`), mais um worker genérico sem filtro. A fila Postgres usa a coluna **`Job.model_alias`**: cada worker só consome jobs cuja `model_alias` coincide com o filtro.

- **Configuração opcional:** variável de ambiente **`LLM_WORKERS_JSON`** — JSON, ex. `{"fast":2,"compact":1,"smart":1,"reasoner":1}`. Se vazio ou inválido, usa-se um worker por alias.
- **Warm-up:** após triagem no `/router`, pode disparar-se `speculative_warmup` no Ollama para o alias escolhido (não bloqueia a resposta HTTP).

### Fluxo Crítico de uma Pergunta

```python
# 1. Cliente POST /ask
POST /ask
{
  "project_id": "bikeanjoall_2026",
  "question": "Qual o horário?",
  "user_id": "5511999990000"
}

# ↓ [api/ask.py] cria job com status "queued"

# 2. Background worker [jobs/worker.py] processa
process_job():
  ├─ load project
  ├─ retrieve(question) → chunks  [rag/retrieve.py]
  ├─ load user profile + history  [db.py]
  ├─ build_messages()             [rag/prompt.py]
  ├─ ollama.chat()
  ├─ persist answer + sources
  └─ mark job as "done"

# 3. Cliente GET /status/{job_id}, /result/{job_id}
GET /status/{job_id} → {"status": "done", ...}
GET /result/{job_id} → {"answer": "...", "sources": [...]}
```

---

## Padrões de Código

### Documentação vs. comentários no código

Comentários e docstrings: **inglês**; só onde o código não for auto-explicativo (invariantes, edge cases, integrações não óbvias). Contratos HTTP e exemplos: `docs/` ([02-api-integration.md](./02-api-integration.md)), não blocos longos nos handlers.

### 1. Funções Async/Await

Toda função que faz I/O (database, HTTP, Ollama) deve ser `async`:

```python
# Evitar
def get_user(user_id: str) -> dict:
    cursor.execute("SELECT * FROM user_profile WHERE user_id = %s")
    return cursor.fetchone()

# Preferir
async def get_user(user_id: str) -> dict:
    query = "SELECT * FROM user_profile WHERE user_id = %s"
    result = await db.fetch_one(query, user_id)
    return result
```

### 2. Uso de asyncpg para Database

```python
import asyncpg

# Pool global (em app/db.py)
pool: asyncpg.Pool | None = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))

async def fetch_one(query: str, *args) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None

async def fetch_all(query: str, *args) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]

# Uso
user = await fetch_one("SELECT * FROM user_profile WHERE id = $1", user_id)
```

### 3. Uso de Registry para Projeto

Sempre carregue projeto via `registry.get_project()`:

```python
from app.registry import get_project, get_rag_policies

# Em qualquer handler
project = await get_project(project_id)
if not project:
    raise HTTPException(status_code=404, detail="project not found")

policies = get_rag_policies(project)
max_chunks = policies.get("max_chunks_to_retrieve", 5)
```

### 4. Error Handling

```python
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

# Em endpoints
@app.post("/ask")
async def handle_ask(req: AskRequest):
    try:
        project = await get_project(req.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="project not found")
        # ... resto da lógica
    except HTTPException:
        raise  # FastAPI trata
    except Exception as e:
        logger.exception("unexpected error in /ask")
        raise HTTPException(status_code=500, detail="internal server error")
```

### 5. Logging

```python
import logging

logger = logging.getLogger(__name__)

# Use níveis apropriados
logger.debug("Carregando chunks para pergunta: %s", question)
logger.info("Job %s iniciado", job_id)
logger.warning("Chunk distante descartado: distance=%f", distance)
logger.error("Falha ao conectar em Ollama", exc_info=True)
```

### 6. Type Hints (Obrigatório)

```python
# Preferir
async def build_messages(
    project: dict,
    question: str,
    chunks: list[dict],
    user_profile: dict | None = None,
) -> tuple[str, str]:
    """
    Build system and user prompts.

    Args:
        project: Project metadata (from registry)
        question: User question
        chunks: Retrieved RAG chunks
        user_profile: Optional user profile for personalization

    Returns:
        (system_message, user_message)
    """
    system_msg = ...
    user_msg = ...
    return system_msg, user_msg

# Evitar
def build_messages(project, question, chunks, user_profile=None):
    ...
```

---

## Adicionar Endpoints

### Exemplo: Novo Endpoint POST /projects/{project_id}/feedback

**Passo 1: Define Pydantic model** (`app/api/projects.py`)

```python
from pydantic import BaseModel

class ProjectFeedbackRequest(BaseModel):
    rating: int  # 1-5
    notes: str | None = None
```

**Passo 2: Cria função no módulo apropriado** (`app/db.py`)

```python
async def project_set_feedback(project_id: str, rating: int, notes: str | None) -> None:
    """Store project feedback in database."""
    query = """
    UPDATE "Project"
    SET feedback_rating = $1, feedback_notes = $2, updated_at = NOW()
    WHERE project_id = $3
    """
    await execute(query, rating, notes, project_id)
```

**Passo 3: Implementa handler** (`app/api/projects.py`)

```python
from fastapi import APIRouter, HTTPException, Header
from app.api.projects import ProjectFeedbackRequest

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("/{project_id}/feedback")
async def submit_project_feedback(
    project_id: str,
    req: ProjectFeedbackRequest,
    authorization: str = Header(None),
) -> dict:
    """Submit feedback about a project."""
    # Validar token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or invalid token")

    token = authorization.split(" ")[1]
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="invalid token")

    # Verificar que projeto existe
    project = await get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    # Salvar feedback
    await db.project_set_feedback(project_id, req.rating, req.notes)

    return {
        "project_id": project_id,
        "feedback_received": True,
        "message": "Obrigado por seu feedback!"
    }
```

**Passo 4: Registra em `main.py`**

```python
from app.api.projects import router as projects_router

app.include_router(projects_router)
```

**Passo 5: Testa localmente**

```bash
# Com servidor rodando
curl -X POST http://127.0.0.1:28471/projects/bikeanjoall_2026/feedback \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"rating": 5, "notes": "Excellent!"}'
```

---

## Estender RAG

### Caso 1: Adicionar novo tipo de source (ex: PDFs)

**Arquivo relevante:** `app/ingest/indexer.py`

```python
# Linha ~45: Extensões suportadas
SUPPORTED_EXTENSIONS = [".txt", ".md", ".markdown", ".rst", ".json", ".pdf"]

# Linha ~70: Ler arquivo (adicione handler PDF)
if file.suffix == ".pdf":
    text = extract_pdf_text(file)
else:
    text = file.read_text(encoding="utf-8")

# Função nova
def extract_pdf_text(file_path: Path) -> str:
    """Extract text from PDF using pypdf or similar."""
    try:
        import pypdf
        with open(file_path, "rb") as f:
            pdf = pypdf.PdfReader(f)
            text = ""
            for page in pdf.pages:
                text += page.extract_text()
        return text
    except ImportError:
        logger.warning("pypdf not installed; skipping PDF %s", file_path)
        return ""
```

### Caso 2: Customizar retrieval (ex: filtro por tag)

**Arquivo relevante:** `app/rag/retrieve.py`

```python
async def retrieve(
    project_id: str,
    question: str,
    top_k: int = 5,
    embedding_model: str = "mxbai-embed-large",
    tag_filter: str | None = None,  # ← Novo parâmetro
) -> list[dict]:
    """Retrieve chunks with optional tag filtering."""

    # Gerar embedding
    embedding = await embeddings.embed(question, embedding_model)

    # Buscar em Chroma
    collection = client.get_collection(project_id)
    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k * 2,  # Recuperar mais para filtrar depois
        where={"tag": tag_filter} if tag_filter else None,
    )

    # ... resto do processamento
    return chunks[:top_k]
```

### Caso 3: Adicionar re-ranking por diversidade

**Arquivo novo:** `app/rag/reranker.py`

```python
def diversity_rerank(chunks: list[dict], max_chunks: int = 5) -> list[dict]:
    """Select chunks with maximum diversity (avoid redundancy)."""
    if len(chunks) <= max_chunks:
        return chunks

    selected = [chunks[0]]
    for chunk in chunks[1:]:
        if len(selected) >= max_chunks:
            break

        # Calcular dissimilaridade
        score = min(
            cosine_distance(chunk["embedding"], s["embedding"])
            for s in selected
        )
        if score > 0.3:  # Threshold de diversidade
            selected.append(chunk)

    return selected
```

**Usar em `worker.py`:**

```python
from app.rag.reranker import diversity_rerank

chunks = await retrieve(project_id, question, top_k=7)
chunks = _filter_chunks_by_distance(chunks)
chunks = diversity_rerank(chunks, max_chunks=5)  # ← Novo
```

---

## Calibração e desvios da LLM

Ao alterar o **system prompt** (`app/rag/prompt.py`), o **worker** (`app/jobs/worker.py`) ou as instruções por projeto, consulte [07-llm-calibration.md](./07-llm-calibration.md). Esse documento descreve os desvios conhecidos, mitigações implementadas e boas práticas.

### Como adicionar regras de sanitização

Regras de sanitização ficam em `app/jobs/worker.py` na função `_sanitize_answer()`. Para adicionar uma nova regra:

1. **Identifique o padrão** em respostas reais (jobs/logs). Documente o exemplo concreto.
2. **Escreva a regex/substituição** de forma conservadora — prefira falso-negativo a falso-positivo.
3. **Adicione à função** `_sanitize_answer()` com comentário explicando: que desvio corrige, quando foi adicionada, exemplo do problema.
4. **Atualize 07-llm-calibration.md** (§ 7) com a nova regra, motivo e resultado esperado.
5. **Teste** com queries reais para verificar que respostas legítimas não são afetadas.

### Parâmetros configuráveis por projeto

| Campo em `config_json.policies` | Default | Onde atua |
|--------------------------------|---------|-----------|
| `max_chunks_to_retrieve` | 5 | `retrieve()` — quantos chunks buscar |
| `max_chunk_distance` | 1.0 | `worker.py` — filtro de relevância (cosine, 0.0-2.0) |
| `when_no_answer` | "no_answer" | `worker.py` — status quando sem chunks |
| `prefer_cite_sources` | true | `prompt.py` — incluir fontes no prompt |

---

## Testes

### Setup de Testes

```bash
# Instalar dependências de teste
pip install pytest pytest-asyncio httpx

# Rodar todos os testes
pytest tests/ -v

# Rodar teste específico
pytest tests/test_rag.py::test_retrieve -v
```

### Exemplo: Teste de Endpoint

```python
# tests/test_api_ask.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

@pytest.fixture
async def setup_project():
    """Create test project in DB."""
    # Seed de test
    await db.execute("""
    INSERT INTO "Project" (id, project_id, name, sources)
    VALUES (..., 'test_project', 'Test', ARRAY['/test'])
    """)
    yield
    # Cleanup
    await db.execute("DELETE FROM \"Project\" WHERE project_id = 'test_project'")

def test_ask_missing_project():
    """Test /ask with non-existent project."""
    resp = client.post(
        "/ask",
        json={"project_id": "nonexistent", "question": "test"},
        headers=HEADERS,
    )
    assert resp.status_code == 404

def test_ask_success(setup_project):
    """Test /ask with valid project."""
    resp = client.post(
        "/ask",
        json={"project_id": "test_project", "question": "test question"},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert "status_url" in data
```

### Exemplo: Teste de RAG

```python
# tests/test_rag_retrieve.py
import pytest
from app.rag.retrieve import retrieve

@pytest.mark.asyncio
async def test_retrieve_with_chunks():
    """Test retrieve returns chunks."""
    chunks = await retrieve("bikeanjoall_2026", "Qual o horário?")
    assert isinstance(chunks, list)
    assert all(isinstance(c, dict) for c in chunks)
    assert all("distance" in c for c in chunks)

@pytest.mark.asyncio
async def test_retrieve_filters_distance():
    """Test distance filtering."""
    chunks = await retrieve("bikeanjoall_2026", "irrelevant question xyz")
    # Chunks com distance > 1.2 devem ser filtrados
    assert all(c["distance"] <= 1.2 for c in chunks)
```

---

## Troubleshooting

### Problema: "connection refused" em Ollama

**Solução:**
```bash
# Verificar se Ollama está rodando
ollama list

# Se não estiver, iniciar (Mac)
brew services start ollama

# Ou no servidor Linux
docker ps | grep ollama

# Se container não está, iniciar
docker run -d -p 11434:11434 ollama/ollama
```

### Problema: Banco de dados não inicializa

**Solução:**
```bash
# Verificar conexão
psql $DATABASE_URL -c "\dt"

# Se erro de auth
export DATABASE_URL="postgresql://user:newpassword@localhost:5432/llmapi"

# Rodar migrations fresh
python -m prisma migrate reset --force
python scripts/seed_bikeanjoall_2026.py
```

### Problema: Worker não processa jobs

**Solução:**
```bash
# Verificar logs
tail -f logs/worker.log

# Ou em stderr (se rodando com --reload)
# Ver se há erros de import ou async

# Debug: rodar job manualmente
python -c "
import asyncio
from app.jobs.worker import process_job
from app import db

async def test():
    await db.init()
    await process_job('job-uuid', 'project', 'test question')

asyncio.run(test())
"
```

### Problema: Respostas muito lentas (>2min)

**Possíveis causas:**
1. Modelo 8b é inherentemente lento (normal: 30-60s)
2. Muitos chunks recuperados (aumentar MAX_CHUNK_DISTANCE)
3. Ollama sobrecarregado (ver `/metrics`)
4. Database lento (verificar índices)

**Soluções:**
```bash
# Reduzir chunks recuperados
# Em registry.py ou config do projeto
"max_chunks_to_retrieve": 3  # de 5 para 3

# Verificar tempo de cada fase (logs)
# Adicionar debug timing em worker.py
import time
t0 = time.time()
chunks = await retrieve(...)
logger.info("retrieve took %.2fs", time.time() - t0)

# Considerar modelo mais rápido
OLLAMA_MODEL = "mistral:7b-instruct-q4_0"  # +30% mais rápido
```

---

## Contribuindo

### Workflow

1. **Crie branch** com seu upgrade:
   ```bash
   git checkout -b feature/meu-upgrade
   ```

2. **Faça changes**, adicione testes:
   ```bash
   # Editar código
   # Adicionar testes em tests/
   # Verificar tudo passa localmente
   pytest tests/ -v
   ```

3. **Commit claro:**
   ```bash
   git commit -m "Add diversity re-ranking to RAG retrieval

   - Implement diversity_rerank() in app/rag/reranker.py
   - Update worker.py to call reranker after filtering
   - Add test in tests/test_rag_reranker.py
   - Reduces redundant chunks by 40%"
   ```

4. **Push e PR** (veja `01_rules.md`)

### Código Style

- **Linter:** `black` (auto-format)
- **Type checker:** `mypy` (type hints obrigatórios)
- **Docstrings:** Sphinx format (veja `build_messages()`)

```bash
# Antes de commit
black app/ tests/
mypy app/ --ignore-missing-imports
```

---

## Referências

- FastAPI: https://fastapi.tiangolo.com/
- asyncpg: https://magicstack.github.io/asyncpg/
- Ollama Python: https://github.com/ollama/ollama-python
- Chroma: https://docs.trychroma.com/

---

**Mais dúvidas?** Abra issue no repositório com `[DEV]` no título.

---

**Anterior:** [03-api-reintegration.md](./03-api-reintegration.md) · **Seguinte:** [05-architecture.md](./05-architecture.md)
