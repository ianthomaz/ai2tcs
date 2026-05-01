# nabilVideoMap — POST /nabilvideomap/qualify-caption

Endpoint **síncrono** da API LLM local (`featureLLM`) para catalogar **uma legenda de Instagram** (texto em português, conteúdo urbano/político de São Paulo) num **JSON fixo** pronto para gravar numa linha SQLite no pipeline nabilVideoMap.

- **Auth:** igual ao resto da API — `Authorization: Bearer` com token global (`LLM_API_TOKEN`) ou chave de projeto `itcs_<project_id>_<hex>`. Com chave de projeto, o `project_id` no corpo JSON deve coincidir com o da chave (comportamento já descrito em `MANUAL_INTEGRACAO.md` / `MANUAL_REINTEGRACAO.md`).
- **Contrato:** caminhos e chaves estáveis para este produto; evoluções futuras podem usar novo path ou v2.

## Pedido

`POST /nabilvideomap/qualify-caption`

Corpo JSON:

| Campo | Obrigatório | Descrição |
|--------|-------------|-----------|
| `project_id` | sim | Ex.: `nabilvideomap` |
| `text` | sim | Só o corpo da legenda (UTF-8), sem métricas de rede |
| `use_rag` | não | Default `false`. Se `true`, injeta trechos do índice Chroma do projeto (mesmo mecanismo de embeddings/retrieve que `/ask`). |
| `model` | não | Alias `fast`, `compact`, `smart`, `reasoner`, ou nome Ollama explícito. Default efetivo: **`smart`**. |

Limite de tamanho: o texto da legenda é recusado com **422** se exceder **16000** caracteres.

## Resposta 200

Objeto JSON com **sempre** estas chaves:

- `location_accuracy` — `clear` \| `partial` \| `weak` \| `none` \| `conflicting`
- `location_granularity` — `neighborhood` \| `street` \| `poi` \| `zone` \| `citywide` \| `multiple` \| `unknown` \| `none`
- `location_primary_label` — string
- `llm_location_candidates` — **array JSON** de objetos `{ "label", "kind", "confidence" }` onde `kind` usa o mesmo conjunto que `location_granularity`; `confidence` opcional, 0–1
- `location_ambiguity_notes` — string
- `location_confidence` — número 0–1 ou **`null`** (chave sempre presente)
- `theme_primary`, `theme_secondary`, `theme_tags`, `llm_theme_notes` — strings
- `summary_140` — string; o servidor **trunca** para no máximo **140 codepoints** Unicode (comprimento em Python `len(...)`). Pode diferir ligeiramente de “140 caracteres” em redes sociais quando há emojis compostos (grafemas).

Enums devolvidos pelo modelo são normalizados para **minúsculas**; valores inválidos após retries geram **422**.

## RAG vazio

Se `use_rag` é `true` mas não há chunks acima do limiar de distância configurado no projeto, o prompt indica explicitamente **só legenda** — resposta baseada apenas no texto, sem contexto indexado.

Cada chamada bem-sucedida ou falha **regista uma linha na tabela `Job`** do Postgres (`job_kind`: `nabil_qualify_caption`, estado `done` ou `failed`, sem passar pela fila `queued`) para o **dashboard** e estatísticas (últimas 24 h, totais por projeto). O tempo médio de jobs na API **exclui** este tipo na média para não distorcer com conclusões síncronas instantâneas.

## Erros

- **404** — `project_id` não existe na base de projetos.
- **422** — após **até 3** chamadas ao modelo (1 + 2 retries), ainda falha parse JSON, enums, ou validação do schema.
- **503** — falha de infraestrutura ao falar com o Ollama (rede, serviço indisponível, etc.); `detail` é string legível por máquina (prefixo `ollama_error:`).

## Variáveis de ambiente

| Variável | Efeito |
|----------|--------|
| `NABIL_QUALIFY_NUM_PREDICT` | Teto de tokens de **saída** (`num_predict`) pedido ao Ollama (default no código: 1536). |
| `NABIL_QUALIFY_NUM_PREDICT_HARD_MAX` | Teto **absoluto** aplicado em cima do valor acima (default 2048). O valor efetivo é `max(256, min(predict, hard_max))`. |
| `NABIL_QUALIFY_RAG_CONTEXT_MAX_CHARS` | Máximo de caracteres concatenados dos snippets RAG no prompt (default 8000). |

## Exemplo curl

```bash
curl -sS -X POST "http://127.0.0.1:28471/nabilvideomap/qualify-caption" \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id":"nabilvideomap","text":"Legenda de exemplo sobre a cidade.","use_rag":false,"model":"smart"}'
```

(Docker na mesma máquina: URL típica `http://127.0.0.1:28471` se a API publicar essa porta.)

## CI / golden set

Testes de regressão com um conjunto fixo de legendas (ex.: 20) em CI são **opcionais / fase 2**; o PR do endpoint inclui testes unitários com Ollama mockado.
