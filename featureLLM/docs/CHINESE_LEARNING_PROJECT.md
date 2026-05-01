# Projeto `chinese_learning` (site Chinês básico / aulaChines)

## Onde está o código

- Repositório: `~/Documents/projects/chineseLearning`
- RAG (markdown): `chineseLearning/rag_knowledge/`
- Web Next.js: `chineseLearning/web/` — tutor chama `POST /api/chat` → proxy para **`POST /edu/chat`**

## Credenciais

- **Um único token** para a API: `LLM_API_TOKEN` em **`featureLLM/.env`** (Mac mini / onde o Docker corre).
- O site local usa o **mesmo** valor em **`chineseLearning/web/.env.local`** (`LLM_API_TOKEN=...`).
- Não commitar `web/.env.local`; o mapa geral de credenciais fica no workspace ITCS privado (ver README na raiz do repo ai2tcs).

## Docker (featureLLM)

O `docker-compose.yml` monta `~/Documents/projects` em modo leitura; dentro do container o path absoluto **`/Users/ianthomaz/Documents/projects/chineseLearning/rag_knowledge`** existe e serve para ingest.

## Variável de ambiente (override opcional)

Em `featureLLM/.env`:

```env
CHINESE_LEARNING_SOURCES=/Users/ianthomaz/Documents/projects/chineseLearning/rag_knowledge
```

(`project_id` = `chinese_learning` → chave `CHINESE_LEARNING_SOURCES` em maiúsculas, ver `app/config.py`.)

## Ingest

```bash
cd ~/Documents/projects/chineseLearning/web
npm run ingest:rag
```

Ou `curl` manual: ver `chineseLearning/connectLLM/RAG_PROJETOS_INGEST_ASK.md`.

## Modelo LLM (DeepSeek / Qwen) no tutor

O `/edu/chat` aceita o campo opcional **`model`** com os mesmos aliases da fleet: `fast`, `compact`, `smart`, **`reasoner`** (mapeado para `OLLAMA_REASONER_MODEL`, por defeito `deepseek-r1:8b`).

**Recomendado para este projeto (sem mudar o resto da API):** no proxy Next.js que chama `POST /edu/chat`, enviar sempre `"model": "reasoner"` (ou só em níveis HSK mais altos / quando o utilizador pede explicação longa). Assim só o site de chinês usa o reasoner; outros clientes EDU continuam com o default.

**Alternativa global na API:** em `featureLLM/.env`, `EDU_CHAT_DEFAULT_MODEL_ALIAS=reasoner` — passa a valer para **todos** os `/edu/chat` que não mandam `model` (útil se só existir o chinês nesta instância).

Trade-off: o R1 é **mais lento** e consome mais RAM; para respostas curtas em JSON estruturado, `smart` ou `compact` podem bastar. Experimenta latência no teu Mac.

## Novo clone / outra máquina

1. Copiar ou gerar token: o valor de `LLM_API_TOKEN` no `.env` da **featureLLM** dessa máquina.
2. Preencher `chineseLearning/web/.env.local`.
3. Ajustar `CHINESE_LEARNING_SOURCES` e o volume em `docker-compose` se o repo não estiver em `~/Documents/projects`.
