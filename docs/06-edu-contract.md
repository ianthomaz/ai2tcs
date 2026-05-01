# 06 — Contrato educacional (/edu/*)

O eixo educacional da LLM é focado em fornecer suporte didático para aprendizado de idiomas (inicialmente Mandarim), permitindo conversas tutoradas, geração de exercícios e acompanhamento de progresso.

Este ficheiro faz parte do repositório **ai2tcs**, em `docs/`.

**Integração:** URL base, autenticação Bearer e visão geral dos endpoints na mesma API que o resto do serviço — ver [02-api-integration.md](./02-api-integration.md) § 3.8 e § 2.

## Visão Geral

- **Base de Conhecimento:** Vocabulário e gramática estruturados no PostgreSQL.
- **Modelos de IA:** O corpo pode incluir `"model": "fast" | "compact" | "smart" | "reasoner"` (alias da fleet). **`reasoner`** usa o modelo configurado em `OLLAMA_REASONER_MODEL` (ex. DeepSeek R1) — útil para explicações mais densas em mandarim; **`smart`** continua a boa escolha por defeito para qualidade pedagógica equilibrada.
- **Sincronismo:** Todas as rotas são síncronas, otimizadas para respostas rápidas.

## Endpoints

### 1. Chat Didático
`POST /edu/chat`

Conversa guiada por um tutor de IA que conhece o nível do aluno e vocabulário relevante.

**Latência:** por defeito o servidor usa o alias em **`EDU_CHAT_DEFAULT_MODEL_ALIAS`** (por omissão `fast`, ex. `llama3:8b`) e limite ~512 tokens. O cliente pode enviar **`"model": "smart"`**, **`"compact"`** ou **`"reasoner"`** (DeepSeek R1) por pedido. Variáveis: `EDU_CHAT_DEFAULT_MODEL_ALIAS`, `EDU_CHAT_NUM_PREDICT`, `EDU_CHAT_TEMPERATURE`, etc. — ver `.env.example`.

**Request Body:**
```json
{
  "message": "Como digo 'bom dia'?",
  "user_id": "whatsapp:+5511999999999",
  "level": "HSK1",
  "language": "zh-CN",
  "history": [
    {"role": "user", "text": "Oi!"},
    {"role": "assistant", "text": "你好 (Nǐ hǎo) — Olá!"}
  ]
}
```

**Response Body (HTTP 200):**

O tutor é instruído a devolver **apenas** um objeto JSON com `reply_structured` e `full_reply_text`. O backend **valida** cada segmento: `hanzi` e `pinyin` não vazios, `translation.pt` não vazio (`en` / `es` podem ser `""`). Se a primeira resposta falhar o schema, a API faz **um retry** automático (mensagem de correção ao modelo, temperatura mais baixa). Se ainda falhar, devolve uma **resposta estruturada fixa** (um segmento em hanzi + pinyin + PT) para o front **nunca** ficar sem toggles. Em todos os casos de sucesso HTTP, `reply_structured` e `full_reply_text` vêm **preenchidos**.

Logs (nível INFO): `level`, número de segmentos, se houve retry, se houve fallback fixo, duração em ms.

```json
{
  "reply": "你好！你想学习什么？",
  "language": "zh-CN",
  "full_reply_text": "你好！你想学习什么？",
  "reply_structured": [
    {
      "hanzi": "你好！",
      "pinyin": "Nǐ hǎo!",
      "translation": {
        "pt": "Olá!",
        "en": "Hello!",
        "es": "¡Hola!"
      }
    },
    {
      "hanzi": "你想学习什么？",
      "pinyin": "Nǐ xiǎng xuéxí shénme?",
      "translation": {
        "pt": "O que você quer estudar?",
        "en": "What do you want to study?",
        "es": "¿Qué quieres estudiar?"
      }
    }
  ]
}
```

- **reply** — Hanzi da resposta: igual a `full_reply_text` quando a resposta vem do modelo ou do fallback fixo.
- **reply_structured** — Lista não vazia em sucesso; cada item com `hanzi`, `pinyin`, `translation` (`pt` obrigatório no conteúdo; `en` / `es` opcionais).
- **full_reply_text** — Linha completa em hanzi (concatenação esperada dos segmentos).

**Nota:** `POST /ask` (RAG) continua a devolver resposta assíncrona com campo `answer` em texto; o formato estruturado acima aplica-se ao **`POST /edu/chat`**.

#### Uso no cliente (sites / apps)

1. **HTTP 200:** assumir sempre **`reply_structured`** com pelo menos um segmento (toggles de Pinyin / Tradução por frase). O conteúdo pode ser o tutor real ou o **segmento fixo** de “tenta de novo” se o modelo falhou duas vezes o schema.
2. Para cada item, mostrar `hanzi` e, conforme o idioma do site, `translation.pt` / `en` / `es` (strings vazias = não mostrar essa língua).
3. **`full_reply_text`:** linha única em hanzi (copiar, TTS).
4. **Regras pedagógicas** são aplicadas via prompt (nível HSK, frases curtas, limite de palavras novas, etc.).
5. **`history`:** podes enviar turnos `assistant` como texto simples (`reply` / `full_reply_text`); o formato da **resposta** mantém-se JSON estruturado via API.

**Exemplo `curl`:**

```bash
curl -s -X POST "$LLM_API_URL/edu/chat" \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Como digo olá?","level":"HSK1","language":"zh-CN"}'
```

---

### 2. Geração de Exercícios
`POST /edu/exercise`

Gera exercícios baseados em uma lista de vocabulário ou no nível do aluno.

**Request Body:**
```json
{
  "user_id": "user123",
  "level": "HSK1",
  "count": 3,
  "exercise_types": ["fill_blank", "translation"]
}
```

**Response Body:**
```json
{
  "language": "zh-CN",
  "level": "HSK1",
  "exercises": [
    {
      "type": "translation",
      "prompt": "Traduza: 你好",
      "answer": "Olá",
      "options": ["Olá", "Obrigado", "Adeus", "Por favor"],
      "hint": "É a saudação mais comum.",
      "vocab_id": "uuid-da-palavra"
    }
  ],
  "count": 1
}
```

---

### 3. Gerenciamento de Vocabulário
`GET /edu/vocabulary` — Listar vocabulário (filtros: `language`, `level`, `limit`, `offset`)
`POST /edu/vocabulary` — Adicionar novo item de vocabulário

**Exemplo de Item:**
```json
{
  "hanzi": "谢谢",
  "pinyin": "xièxie",
  "translation": "obrigado",
  "level": "HSK1",
  "category": "expressão",
  "example_sentence": "谢谢老师",
  "example_pinyin": "Xièxie lǎoshī",
  "example_translation": "Obrigado, professor"
}
```

---

### 4. Gerenciamento de Gramática
`GET /edu/grammar` — Listar pontos gramaticais
`POST /edu/grammar` — Adicionar ponto gramatical

**Exemplo de Ponto Gramatical:**
```json
{
  "pattern": "A 是 B",
  "explanation": "Verbo de ligação 'ser' para conectar dois substantivos.",
  "level": "HSK1",
  "examples": [
    {"hanzi": "我是学生", "pinyin": "Wǒ shì xuésheng", "translation": "Eu sou estudante"}
  ]
}
```

---

### 5. Registro de Progresso
`POST /edu/progress`

Registra se o usuário acertou ou errou um item de vocabulário. Após 5 acertos, o item é marcado como `mastered`.

**Request Body:**
```json
{
  "user_id": "user123",
  "vocab_id": "uuid-da-palavra",
  "correct": true
}
```

**Response Body:**
```json
{
  "user_id": "user123",
  "vocab_id": "uuid-da-palavra",
  "seen_count": 5,
  "correct_count": 3,
  "mastered": false
}
```

## Fluxo Recomendado

1. **Onboarding:** Identifique o nível do aluno (ex: HSK1).
2. **Prática:** Use o `/edu/chat` para conversas livres ou dúvidas; no frontend, prefira renderizar `reply_structured` quando existir para alinhar Pinyin e traduções ao idioma do site (`pt` / `en` / `es`).
3. **Reforço:** Gere exercícios via `/edu/exercise`.
4. **Acompanhamento:** Registre cada resposta via `/edu/progress` para personalizar futuras sessões.

---

**Anterior:** [05-architecture.md](./05-architecture.md) · **Seguinte:** [07-llm-calibration.md](./07-llm-calibration.md)
