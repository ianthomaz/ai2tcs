# 12 — Operações: fleet de modelos, RAG e embeddings

Guia **único** para operar a API LLM após mudanças de modelos Ollama, perceber o que fica no **repo** vs no **servidor/BD**, e saber o que falta para ganhos grandes de qualidade (ver também [11-improvements-roadmap.md](./11-improvements-roadmap.md)).

**Anterior:** [11-improvements-roadmap.md](./11-improvements-roadmap.md) · **Seguinte:** [01-overview.md](./01-overview.md) (índice)

---

## 1. O que já está definido no código (repo)

| Alias / uso | Default Ollama (tag) | Onde |
|---------------|----------------------|------|
| `smart` | `gemma3:12b` | `llm_api/app/config.py` → `OLLAMA_SMART_MODEL` |
| `reasoner` | `deepseek-r1:14b` | `OLLAMA_REASONER_MODEL` |
| Chat legacy | `gemma3:12b` | `OLLAMA_CHAT_MODEL` |
| Embedding **fallback** (sem campo no projecto) | `mxbai-embed-large` | `ingest/embeddings.py`, `indexer.py`, `worker.py`, `rag/retrieve.py`, etc. |

Seeds (`scripts/seed_*.py`) gravam `embedding_model` nos projectos **novos** alinhado ao repo.

---

## 2. Apps que **consomem** esta API (fora deste repo)

**Em regra não precisam de alteração** se usam aliases (`smart`, `reasoner`, …) e `project_id` como sempre.

Só precisam mudança se tiverem **nome de modelo Ollama fixo** no JSON (ex.: `qwen2.5:14b-instruct`) e esse modelo deixar de existir no servidor.

---

## 3. Servidor: checklist após `git pull`

1. **`ollama pull`** dos tags que a instância usa (mínimo sugerido):
   - `gemma3:12b`
   - `deepseek-r1:14b`
   - `mxbai-embed-large`
2. **`llm_api/.env`** (ficheiro real, não versionado): `OLLAMA_SMART_MODEL`, `OLLAMA_REASONER_MODEL`, `OLLAMA_CHAT_MODEL` se quiseres override.
3. **Reiniciar** o processo da API (Docker / systemd / script local).

**Docker Compose:** o serviço `api` usa `env_file: .env` em `llm_api/docker-compose.yml` para o contentor herdar o **`llm_api/.env` completo**; as variáveis listadas em `environment:` (ex.: `DATABASE_URL` para o host `postgres`) **sobrepõem** o ficheiro. Sem `.env` no disco, `docker compose up` falha — copiar de `.env.example` primeiro.

**Sincronizar `.env` com o exemplo (mantém tokens e OAuth):** a partir da pasta `llm_api/`, `python3 scripts/merge_env_from_example.py` — reescreve `.env` na ordem do `.env.example`, preserva valores já definidos e acrescenta chaves novas do exemplo (prefixos seguros como `OLLAMA_*` passam a linhas activas com default do exemplo se ainda não existirem).

Não existe variável de ambiente única que substitua o **`embedding_model` por projecto** na BD; o fallback no código só aplica quando o campo **não** está no `config_json`.

---

## 4. Embeddings e RAG: o que **não** se perde sozinho

- Índices Chroma ficam em **disco** (`data_dir` da instância). Um `git pull` **não** apaga ingest antigo.
- **Trocar** `embedding_model` de um projecto (ex.: `nomic-embed-text` → `mxbai-embed-large`) implica **dimensões de vector diferentes** → é obrigatório **re-ingestar** esse projecto (e limpar/recriar a coleção desse projecto se a ferramenta de ingest não substituir tudo automaticamente).

---

## 5. Onde editar `embedding_model` (gestão do projecto)

| Via | Suporta `embedding_model`? |
|-----|----------------------------|
| **Dashboard** `/dashboard/projects/{id}` — campo *Modelo de embedding (Ollama)* | Sim (formulário “Editar Projeto”). Vazio = remove o campo e usa o **fallback do código**. |
| **API** `PUT /projects/{project_id}` com `config_json` | Sim |
| **SQL / Prisma Studio** | Sim |

O resto do `config_json` (chunking, políticas, etc.) mantém-se ao gravar pelo dashboard; só se sobrepõem `llm_options`, `embedding_model` e campos do formulário.

---

## 6. Checklist por projecto (quando fores “avulso”)

[ ] Confirmar tag Ollama instalada (`ollama list`).  
[ ] No dashboard (ou API): `embedding_model` desejado **ou** vazio para default global.  
[ ] Se mudaste embedding face ao índice actual: **re-ingest** das sources desse `project_id`.  
[ ] Smoke: `POST /ask` ou fluxo que uses com esse `project_id`.

---

## 7. O que mais melhora **muito** o uso de LLMs / RAG (prioridade)

Resumo alinhado ao [roadmap 11](./11-improvements-roadmap.md); **nenhuma dúvida técnica bloqueante** — é sobretudo **priorização e tempo**.

| Prioridade | Item | Porquê |
|------------|------|--------|
| Alta | **Reranker** (cross-encoder) sobre os top-k chunks | Maior salto de qualidade em RAG sem trocar o LLM principal |
| Alta | **Modelos** já alinhados Apple Silicon / Ollama | Velocidade + custo de RAM sob controlo |
| Média | **Hybrid search** (BM25 + vector) | Termos técnicos / nomes próprios |
| Média | **Cache de embeddings** (queries repetidas) | Menos latência e menos carga no Ollama |
| Média | **Streaming** (`/ask` ou equivalente) | UX em respostas longas |
| Média | `OLLAMA_KEEP_ALIVE` para modelos quentes | Menos cold start entre pedidos |

Detalhe de sprints e ideias extra: ficheiro **11**.

---

## 8. Referências cruzadas

| Tema | Doc |
|------|-----|
| Variáveis `OLLAMA_*`, histórico de upgrades | [09-model-upgrade.md](./09-model-upgrade.md) |
| Forma completa de `config_json` | [08-project-config.md](./08-project-config.md) |
| Contratos HTTP | [02-api-integration.md](./02-api-integration.md) |
