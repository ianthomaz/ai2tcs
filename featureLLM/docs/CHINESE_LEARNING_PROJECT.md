# Projeto `chinese_learning` (site Chinês básico / aulaChines)

## Onde está o código

- Repositório do site (exemplo): clone à parte, ex. `~/projects/chineseLearning`
- RAG (markdown): `chineseLearning/rag_knowledge/`
- Web Next.js: `chineseLearning/web/` — tutor chama `POST /api/chat` → proxy para **`POST /edu/chat`**

## Credenciais

- **Um único token** para a API: `LLM_API_TOKEN` em **`featureLLM/.env`** (host onde o Docker corre).
- O site local usa o **mesmo** valor em **`chineseLearning/web/.env.local`** (`LLM_API_TOKEN=...`).
- Não commitar `web/.env.local`.

## Docker (featureLLM)

O `docker-compose.yml` pode montar um diretório pai em modo leitura para o container ver a pasta RAG. Ajusta o **volume** e `CHINESE_LEARNING_SOURCES` ao teu layout — caminhos absolutos reais em `local-only/`.

## Variável de ambiente (override opcional)

Em `featureLLM/.env`:

```env
CHINESE_LEARNING_SOURCES=/caminho/absoluto/para/chineseLearning/rag_knowledge
```

(`project_id` = `chinese_learning` → chave `CHINESE_LEARNING_SOURCES` em maiúsculas, ver `app/config.py`.)

## Ingest

```bash
cd /caminho/para/chineseLearning/web
npm run ingest:rag
```

Ou `curl` manual: ver documentação do projeto `chineseLearning` (se existir).

## Modelo LLM (DeepSeek / Qwen) no tutor

O `/edu/chat` aceita o campo opcional **`model`** com os mesmos aliases da fleet: `fast`, `compact`, `smart`, **`reasoner`**.

**Recomendado para este projeto (sem mudar o resto da API):** no proxy Next.js que chama `POST /edu/chat`, enviar sempre `"model": "reasoner"` (ou só em níveis HSK mais altos). Assim só o site de chinês usa o reasoner; outros clientes EDU continuam com o default.

**Alternativa global na API:** em `featureLLM/.env`, `EDU_CHAT_DEFAULT_MODEL_ALIAS=reasoner` — vale para **todos** os `/edu/chat` sem `model`.

Trade-off: o R1 é **mais lento** e consome mais RAM; para respostas curtas em JSON estruturado, `smart` ou `compact` podem bastar.

## Novo clone / outra máquina

1. Copiar ou gerar token: `LLM_API_TOKEN` no `.env` da **featureLLM** dessa máquina.
2. Preencher `chineseLearning/web/.env.local`.
3. Ajustar `CHINESE_LEARNING_SOURCES` e volumes em `docker-compose` ao caminho real do clone.
