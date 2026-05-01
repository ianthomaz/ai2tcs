# 11 — Roadmap de Melhorias: Mais Inteligente, Rápido e Acessível

> Contexto: Mac com 32 GB RAM dedicado (Apple Silicon), Ollama como backend, Chroma para vetores, FastAPI + PostgreSQL.

---

## TL;DR — Prioridades por impacto

| Prioridade | Área | Ganho |
|---|---|---|
| 🔴 Alta | Modelos Apple Silicon | +30–70% velocidade de inferência |
| 🔴 Alta | Reranker semântico (RAG) | +qualidade de resposta significativa |
| 🟡 Média | Cache de embeddings | −latência, −custo de CPU |
| 🟡 Média | Hybrid Search (BM25 + vetor) | +precisão em termos exatos |
| 🟡 Média | Streaming de respostas | melhor UX |
| 🟢 Baixa | Prompt compression | −tokens, +contexto disponível |
| 🟢 Baixa | Avaliação automatizada (evals) | qualidade mensurável |

---

## 1. Modelos — O que vale a pena rodar no Mac 32 GB

### O que já temos

```
fast      → llama3:8b
compact   → qwen2.5:7b-instruct
smart     → qwen2.5:14b-instruct
reasoner  → deepseek-r1:8b
```

### O que 32 GB suporta bem (Apple Silicon = UMA = CPU+GPU compartilhada)

| Modelo | Tamanho (Q4) | Uso sugerido | Velocidade aprox. |
|---|---|---|---|
| `gemma3:12b` | ~8 GB | chat geral, PT-BR muito bom | rápido |
| `qwen2.5:32b-instruct-q4` | ~20 GB | substituir `smart`, respostas melhores | moderado |
| `llama3.3:70b-q2_k` | ~28 GB | raciocínio pesado (cabe, mas lento) | lento |
| `deepseek-r1:14b` | ~9 GB | reasoning + CoT, melhor que :8b | moderado |
| `phi4:14b` | ~9 GB | Microsoft, bom em código e PT | rápido |
| `mistral-small:22b-q4` | ~13 GB | alternativa equilibrada | moderado |
| `nomic-embed-text:latest` | ~0.3 GB | já em uso — manter | muito rápido |
| `mxbai-embed-large` | ~0.7 GB | embedding melhor que nomic para PT-BR | rápido |

**Recomendação imediata:**
1. Adicionar `gemma3:12b` como alias `smart` (melhor custo/benefício hoje)
2. Adicionar `deepseek-r1:14b` como alias `reasoner` (melhor que :8b)
3. Testar `mxbai-embed-large` como embedding model (melhor recall em português)

```bash
ollama pull gemma3:12b
ollama pull deepseek-r1:14b
ollama pull mxbai-embed-large
```

### Especialistas por domínio

```
Código:       qwen2.5-coder:14b
Visão:        llava:13b ou gemma3:12b (multimodal nativo)
Documentos:   llama3.1:8b (bom summarizer)
Português:    sabia-3 (Maritaca AI, via API — não roda local ainda)
```

---

## 2. RAG — Qualidade de Resposta

### 2.1 Reranker Semântico (maior impacto único)

O Chroma retorna os K chunks mais próximos por cosseno — mas "próximo" em vetor ≠ "mais relevante" para a pergunta. Um reranker lê pares (pergunta, chunk) e pontua relevância real.

**Como adicionar:**

```python
# requirements.txt
sentence-transformers>=3.0
# ou usar via Ollama se disponível

# llm_api/app/rag/rerank.py
from sentence_transformers import CrossEncoder

_reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def rerank(query: str, chunks: list[str], top_k: int = 4) -> list[str]:
    pairs = [(query, c) for c in chunks]
    scores = _reranker.predict(pairs)
    ranked = sorted(zip(scores, chunks), reverse=True)
    return [c for _, c in ranked[:top_k]]
```

Plugar em `rag/retrieve.py` após o fetch do Chroma, antes de montar o prompt.

**Alternativas leves:**
- `cross-encoder/ms-marco-MiniLM-L-6-v2` (~70 MB, rápido)
- `BAAI/bge-reranker-base` (~280 MB, melhor qualidade)

### 2.2 Hybrid Search (BM25 + Vetor)

BM25 é busca por palavras exatas — funciona bem para termos técnicos, siglas (NF-e, CNPJ, CEP), nomes próprios que os embeddings às vezes não capturam.

```python
# pip install rank_bm25
from rank_bm25 import BM25Okapi

def hybrid_retrieve(query, chroma_results, corpus_tokens, alpha=0.5):
    bm25 = BM25Okapi(corpus_tokens)
    bm25_scores = bm25.get_scores(query.split())
    # combinar scores normalizados com alpha
    ...
```

**Ganho:** Especialmente útil para NF extraction e busca de números de processo/CNPJ.

### 2.3 Chunking Contextual

Em vez de chunkar por tamanho fixo, adicionar contexto do documento ao início de cada chunk:

```python
# Antes de indexar:
chunk_with_context = f"[Documento: {doc_title}]\n{chunk_text}"
```

Melhora recall sem mudar a busca. Custo: ~10% mais tokens nos embeddings.

### 2.4 Sentence Window Retrieval

Busca por frases pequenas (melhor semântica), mas retorna janelas maiores (melhor contexto):

- Embeda chunks de 1–2 frases
- Ao recuperar, retorna ±2 frases ao redor (janela de 5)
- Implementar em `rag/retrieve.py` com índice de posição

---

## 3. Performance — Latência e Throughput

### 3.1 Cache de Embeddings

Todo `/ask` recalcula o embedding da pergunta. Cache simples economiza CPU:

```python
import hashlib, functools

@functools.lru_cache(maxsize=512)
def embed_cached(text: str) -> list[float]:
    return ollama.embeddings(model=EMBED_MODEL, prompt=text)["embedding"]
```

Para cache persistente entre restarts, usar Redis ou arquivo pickle com TTL.

### 3.2 Streaming de Respostas (SSE)

O modelo atual usa polling: cliente chama `/ask` → job na fila → poll `/status` → GET `/result`. 

Para sessões interativas, streaming é muito melhor:

```python
# app/api/ask.py — nova rota síncrona com streaming
from fastapi.responses import StreamingResponse

@router.post("/ask/stream")
async def ask_stream(req: AskRequest):
    async def generate():
        async for chunk in ollama_stream(req.question, context):
            yield f"data: {chunk}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Manter o sistema de jobs para integrações assíncronas** (WhatsApp, webhooks) — streaming é complementar, não substituto.

### 3.3 Pré-carregamento de Modelos

Ollama descarrega modelos inativos. Com 32 GB, manter 2 modelos em memória:

```bash
# keep-alive = -1 = nunca descarregar
OLLAMA_KEEP_ALIVE=-1 ollama serve
```

Ou via API:
```bash
curl http://localhost:11434/api/generate -d '{"model":"gemma3:12b","keep_alive":-1}'
```

### 3.4 Concorrência de Workers

Atualmente: 1 worker por vez (asyncio sequential). Ampliar para N workers paralelos:

```python
# config.py
WORKER_CONCURRENCY: int = 3  # 3 jobs simultâneos

# jobs/worker.py
semaphore = asyncio.Semaphore(settings.worker_concurrency)
async def process_job(job_id):
    async with semaphore:
        ...
```

Cuidado: cada Ollama call ocupa GPU/UMA — 3 jobs paralelos + modelo grande pode causar swap.

### 3.5 Quantização e Tamanho de Contexto

| Config | Velocidade | Qualidade |
|---|---|---|
| Q8 | lento | melhor |
| Q4_K_M | rápido | boa (recomendado) |
| Q2_K | muito rápido | degradada |

No `09-model-upgrade.md` já há orientação. Para PT-BR factual, Q4_K_M é o sweet spot.

Limitar `num_ctx` por alias:
```python
# fast: 2048 tokens
# smart: 4096 tokens
# reasoner: 8192 tokens
```

Contexto menor = resposta mais rápida, memória menor.

---

## 4. Acessibilidade — Integração com Projetos Pessoais

### 4.1 SDK Python Simples

Criar `llm_api/sdk/client.py` para uso em outros projetos:

```python
# pip install ai2tcs-client  (futuro)
from ai2tcs import LLMClient

client = LLMClient(base_url="http://localhost:28471", api_key="itcs_...")

# Síncrono
answer = client.ask("Como funciona a tração traseira?", project="bikeanjoall_2026")

# Streaming
for chunk in client.ask_stream("Explica RAG", project="webplace"):
    print(chunk, end="")
```

### 4.2 CLI Local

```bash
# scripts/ai2tcs-cli
ai2tcs ask "Qual o prazo de renovação da CNH?" --project bikeanjoall
ai2tcs ingest docs/manual.pdf --project webplace
ai2tcs jobs list --status queued
```

Implementar com `click` ou `typer`. 20–30 linhas.

### 4.3 Webhook / Callback de Resultado

Em vez de polling, cliente registra URL e recebe POST quando job completa:

```python
# models.py — adicionar
class AskRequest(BaseModel):
    ...
    callback_url: str | None = None  # POST quando pronto

# worker.py — ao finalizar job
if job.callback_url:
    async with httpx.AsyncClient() as c:
        await c.post(job.callback_url, json={"job_id": job.id, "result": result})
```

Útil para integrações com Zapier, Make, n8n, ou scripts externos.

### 4.4 MCP Server (Model Context Protocol)

Expor o ai2tcs como ferramenta para Claude Code / Claude Desktop:

```python
# mcp_server.py
from mcp.server import Server
app = Server("ai2tcs")

@app.tool()
async def ask_llm(project: str, question: str) -> str:
    """Consulta o LLM local com RAG do projeto especificado."""
    ...
```

Permite usar o sistema diretamente de dentro do Claude Code com `/mcp ai2tcs`.

### 4.5 OpenAI-Compatible Endpoint

Muitas ferramentas (Continue.dev, Open WebUI, LangChain) esperam a API da OpenAI. Adicionar camada de compatibilidade:

```python
@router.post("/v1/chat/completions")
async def openai_compat(req: OpenAIRequest):
    # traduzir para formato interno
    result = await process_ask(req.messages[-1].content, project=req.model)
    return {"choices": [{"message": {"content": result}}]}
```

Isso permite plugar **qualquer cliente OpenAI** direto no ai2tcs.

---

## 5. Inteligência — Respostas Melhores

### 5.1 Self-RAG / Reflexão

Após gerar resposta, rodar uma checagem automática:

```python
REFLECTION_PROMPT = """
Pergunta: {question}
Contexto RAG: {context}
Resposta gerada: {answer}

A resposta está embasada no contexto? Responda: SIM | PARCIAL | NAO
Se PARCIAL ou NAO, corrija a resposta usando apenas o contexto.
"""
```

Roda com modelo `fast` (barato). Filtra alucinações antes de entregar.

### 5.2 Memória de Longo Prazo por Usuário

Além do histórico de conversa, guardar "fatos aprendidos" sobre o usuário:

```sql
-- nova tabela
CREATE TABLE user_memory (
  id SERIAL PRIMARY KEY,
  project_id TEXT,
  user_id TEXT,
  fact TEXT,          -- "Usuário prefere respostas curtas"
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Injetar no system prompt:
```python
memories = await fetch_user_memory(project_id, user_id)
system = f"Sobre este usuário: {'; '.join(memories)}\n\n{base_system}"
```

### 5.3 Roteamento Automático por Complexidade

Já existe `router/selection.py`. Ampliar para rotear por custo de inferência:

```python
def select_model(question: str) -> str:
    if is_simple_lookup(question):   return "fast"    # llama3:8b
    if needs_reasoning(question):    return "reasoner" # deepseek-r1:14b
    return "smart"                                     # gemma3:12b padrão
```

`is_simple_lookup`: pergunta < 10 palavras, sem "por que", "como", "explica"
`needs_reasoning`: contém "calcule", "compare", "analise", "prove"

### 5.4 Few-Shot Dinâmico

Em vez de exemplos fixos no prompt, buscar exemplos relevantes no Chroma:

```python
# Ao montar prompt para edu/extract:
examples = chroma.query(query_texts=[question], where={"type": "example"}, n_results=2)
prompt = few_shot_template(examples) + question
```

Indexar exemplos curados no projeto junto com documentos.

### 5.5 Fallback Gracioso para API Externa

Quando Ollama estiver sobrecarregado ou modelo lento demais:

```python
# config.py
FALLBACK_PROVIDER: str = "none"  # "anthropic" | "openai" | "none"
FALLBACK_LATENCY_THRESHOLD_MS: int = 30000

# worker.py
if elapsed > threshold and settings.fallback_provider == "anthropic":
    return await anthropic_fallback(question, context)
```

Para projetos pessoais: fallback para Claude Haiku (barato) se o Mac estiver lento.

---

## 6. Observabilidade

### 6.1 Métricas de Qualidade RAG

Além das métricas de latência já em `/metrics`, adicionar:

```python
# Para cada job completo:
{
  "chunks_retrieved": 5,
  "chunks_used": 3,        # após rerank
  "avg_chunk_distance": 0.42,
  "answer_length_tokens": 187,
  "model_used": "gemma3:12b",
  "had_rag_context": True
}
```

Salvar em `job_audit` e expor em `/metrics`.

### 6.2 Dashboard de Qualidade

Adicionar aba no dashboard existente (Jinja2/HTMX):
- Histograma de distância média dos chunks (mostra se RAG está funcionando)
- Taxa de jobs sem contexto RAG (indicador de base de conhecimento pobre)
- Tempo médio por modelo

### 6.3 Evals Automatizados

Script para testar qualidade com perguntas gold-standard:

```bash
# scripts/eval_rag.py
python scripts/eval_rag.py --project bikeanjoall --dataset tests/eval_questions.json
```

```json
// tests/eval_questions.json
[
  {"question": "O que é o Bike Anjo?", "expected_keywords": ["voluntário", "ciclismo"]},
  {"question": "Como me tornar um Bike Anjo?", "expected_keywords": ["cadastro", "treinamento"]}
]
```

Roda no CI após cada mudança de prompt ou modelo.

---

## 7. Infraestrutura Mac — Otimizações Específicas

### 7.1 Ollama com Metal GPU

Ollama já usa Metal automaticamente no Apple Silicon. Verificar:

```bash
ollama run gemma3:12b --verbose 2>&1 | grep -i "metal\|gpu"
```

Se não aparecer GPU: reinstalar Ollama via site oficial (não Homebrew para versões antigas).

### 7.2 Memória UMA — Regra Prática

No Apple Silicon, RAM é compartilhada entre CPU e "GPU". Para 32 GB:

| Reserva SO | Disponível LLM |
|---|---|
| ~4 GB | ~28 GB úteis |

Modelos que cabem confortavelmente:
- 1 modelo grande: `qwen2.5:32b-q4` (~20 GB) + sistema rodando
- 2 modelos médios: `gemma3:12b` + `deepseek-r1:14b` (~17 GB) — ideal para produção
- 3 modelos pequenos: `llama3:8b` × 3 ou mix — para testes

### 7.3 Acesso de Outros Projetos na Rede Local

Configurar para aceitar conexões da rede local (sem Tailscale):

```bash
# launchd ou .env
OLLAMA_HOST=0.0.0.0:11434  # Ollama acessível na LAN
API_HOST=0.0.0.0
API_PORT=28471
```

Outros Macs/PCs na mesma rede podem chamar `http://mac-host.local:28471`.

### 7.4 Tailscale para Acesso Remoto Seguro

Já documentado em `refs/operacao-tailscale.md`. Adicionar MagicDNS:

```bash
# Em qualquer dispositivo na sua conta Tailscale:
curl http://mac-llm:28471/health
```

Sem VPN complexa, sem IP fixo.

### 7.5 Inicialização Automática

```bash
# launchd plist para Ollama + ai2tcs na inicialização do Mac
# ~/Library/LaunchAgents/com.itcs.ai2tcs.plist
```

Ver `scripts/llm_docker_autostart.sh` como base — adaptar para launchctl.

---

## 8. Próximos Passos Sugeridos

### Sprint 1 (impacto rápido, ~1 semana)
- [ ] Trocar embedding por `mxbai-embed-large` (melhor PT-BR)
- [ ] Adicionar `gemma3:12b` como `smart`
- [ ] Implementar cache de embeddings com `lru_cache`
- [ ] Configurar `OLLAMA_KEEP_ALIVE=-1` para modelos principais

### Sprint 2 (qualidade RAG, ~2 semanas)
- [ ] Adicionar reranker `cross-encoder/ms-marco-MiniLM-L-6-v2`
- [ ] Implementar streaming endpoint `/ask/stream`
- [ ] Adicionar `callback_url` no job request

### Sprint 3 (acessibilidade, ~2 semanas)
- [ ] SDK Python simples em `llm_api/sdk/`
- [ ] Endpoint OpenAI-compatible `/v1/chat/completions`
- [ ] Script de evals automatizados

### Sprint 4 (inteligência, ~1 mês)
- [ ] Self-RAG / reflexão automática
- [ ] Memória de longo prazo por usuário
- [ ] Roteamento automático por complexidade
- [ ] MCP Server para Claude Code

---

## Referências

- [Ollama Models Library](https://ollama.com/library) — catálogo completo
- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard) — ranking de embedding models
- [BAAI Rerankers](https://huggingface.co/BAAI) — modelos de reranking open-source
- [Model Context Protocol](https://modelcontextprotocol.io) — MCP spec
- [Sentence Transformers](https://www.sbert.net) — cross-encoders para reranking
