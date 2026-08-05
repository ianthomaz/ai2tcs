# 07 — Calibração LLM (desvios e mitigação)

Desvios comuns do modelo local + mitigação na API e por projeto.

---

## 1. Contexto

Modelo local (Ollama, ex. 7B/8B) + RAG: instruções menos estáveis que modelos grandes ou APIs geridas.

Comportamentos típicos:

- Frases-meta de treino ("Com base no contexto…", "Não encontrei informação…").
- Alucinação lexical pontual.
- Tom neutro / autodesvalorizante vs. tom de negócio.

**Calibração:** prompt base + `instrucoes-llm` por projeto + pós-processamento mínimo quando aplicável.

---

## 2. Desvios e dificuldades conhecidas

### 2.1 Frases meta / autodesvalorizantes

A LLM frequentemente **abre ou encadeia** com frases que soam robóticas ou que diminuem a resposta:

| Exemplo de desvio | Problema |
|-------------------|----------|
| "Com base no contexto fornecido, não encontrei..." | Soa como "não sei"; não vende nem direciona. |
| "Segundo o conteúdo," / "Segundo o contexto," | Redundante; o usuário não precisa saber de onde veio. |
| "A pergunta é sobre..." | Repete a pergunta em vez de responder. |
| "Não encontrei informação suficiente na base de conhecimento para responder essa pergunta." | Frase longa e negativa; desvia do foco (oferecer serviço + contato). |
| "Com base apenas na informação fornecida, não há uma resposta direta..." | Mesmo efeito: tom de "não tenho nada" em vez de direcionar. |
| "não encontrei informação específica que justifique ou desaconselhe o contrato" | Neutro/negativo; não ajuda a vender nem a encaminhar. |

**Objetivo:** responder **direto** com o conteúdo relevante; quando não houver, ser breve e direcionar para contato/site, sem encher de justificativas.

### 2.2 Citações internas desnecessárias

- "(como descrito no arquivo 'Como fazer a Declaração Anual do MEI')".
- Referências a "Notion", "links" ou títulos de documentos como se fossem a resposta.

O usuário não tem acesso a arquivos internos. O que importa é o **conteúdo** (o que a Mobi faz, como fazer X) e, quando fizer sentido, **um link externo** (ex.: mobicontabil.com.br).

### 2.3 Alucinações e erros de palavra

- **"falecimento" em contexto de contato:** a LLM às vezes gera "contatos para falecimento ou envio de mensagens" em vez de "fale conosco". É erro de geração (não vem da base).  
  **Mitigação:** correção mínima no worker **só** quando o padrão errado aparece e **não** é contexto de morte (ex.: "falecimento de um sócio" permanece intacto). Ver § 4.

- **"parabéns a um novo empresário" / "abraço da empresa":** confusão com "abertura da empresa". Conteúdo bem escrito na base e instruções de tom ajudam; não há substituição automática.

- **Erros de gramática:** "Você pode abertura", "você pode fale". Instruções pedem resposta direta e natural; reduzir trechos genéricos no prompt ajuda.

### 2.4 Tom neutro ou que não vende

Em projetos como estudiosmobi, o objetivo é **vender serviços** e direcionar para contato. A LLM pode:

- Responder com "recomendo consultar os links" em vez de dizer o que a empresa faz e convidar a falar com a equipe.
- Dar a impressão de "não temos isso" em vez de "isso a gente resolve com você; fale com a gente".

**Mitigação:** mood e regras no **instrucoes-llm.md** do projeto (§ 3) e no **prompt base** (§ 4).

### 2.5 Quando não há informação suficiente

O comportamento desejado quando a base não tem o detalhe:

- **Não:** parágrafo longo explicando que não encontrou informação, nem "não há informações que justifiquem ou desaconselhem".
- **Sim:** uma linha sobre o que o serviço oferece sobre o tema (ex.: "A Mobi faz alteração de empresa.") + convite para falar com a equipe ou acessar o site. Tom de **serviço**, não de desculpa.

---

## 3. O que está implementado

### 3.1 Prompt base (`app/rag/prompt.py`)

- **Calibração obrigatória** no system prompt: responder de forma direta; não usar "Com base no contexto fornecido", "Segundo o conteúdo", "não encontrei informação específica", "A pergunta é sobre" ou similares.
- Quando não houver nada útil no contexto: usar `no_answer_fallback` do `config_json` do projeto (default genérico na API). Projetos de vendas (ex.: estudosMobi) definem fallback com marca própria em `behavior_instruction_path` ou `no_answer_fallback`.
- Assim, **todos os projetos** recebem essa regra; projetos com instruções próprias (ex.: estudiosmobi) somam as deles em cima.

### 3.2 Instruções por projeto (fluxosLLM / behavior_instruction_path)

- O projeto pode ter um arquivo (ex.: `fluxosLLM/instrucoes-llm.md`) cujo conteúdo é **lido em toda pergunta** e injetado no system prompt.
- Uso: **mood** (ex.: vender serviços), proibições explícitas (ex.: "Segundo o contexto", "justifique ou desaconselhe"), tom quando não há informação (oferecer serviço + contato), evitar citações a arquivos.
- Não passa por ingest; é carregado em tempo de request. Ver 02-api-integration.md § 10 e § 13 (estudosmobi — fluxosLLM).

### 3.3 Sanitização mínima no worker (`app/jobs/worker.py`)

- **Apenas um caso:** correção do typo "falecimento" quando é claramente **contexto de contato** (ex.: "contatos para falecimento ou envio de mensagens").
- **Contexto de morte preservado:** se a resposta contiver "falecimento de ", "falecimento do ", "em caso de falecimento", "falecimento de um", **não** se aplica substituição (ex.: "em caso de falecimento de um sócio" permanece correto).
- Nenhuma outra alteração automática no texto da resposta; a API não é comprometida.

### 3.4 Conteúdo e ingest

- Base reduzida e bem estruturada (ex.: 44 arquivos em vez de 260) melhora relevância do retrieve.
- Ingest com normalização de Markdown (remoção de boilerplate de export Notion, "Sobre:", palavras-chave no primeiro chunk) ajuda o ranking. Ver `app/ingest/chunking.py`.
- **Não** criar um doc por tema só para “ranquear”; priorizar **conteúdo único** e instruções de tom.

---

## 4. Boas práticas

1. **Instruções em dois níveis:** prompt base (regras gerais de tom e proibições) + arquivo de projeto (mood, proibições específicas, exemplo de “quando não tem informação”).
2. **Evitar frases longas de fallback** no próprio prompt; preferir “seja breve e sugira contato/site”.
3. **Revisar respostas reais** (logs, jobs) e ir acrescentando proibições ou exemplos no `instrucoes-llm.md` do projeto.
4. **Conteúdo claro na base:** títulos e primeiros parágrafos que deixem explícito o tema (ex.: “O que a Mobi faz”) melhoram retrieve e reduz necessidade de “desculpas”.
5. **Pós-processamento:** usar só para erros **bem identificados** e **contexto-dependentes** (ex.: falecimento vs. fale conosco); não reescrever respostas inteiras.

---

## 5. Limitações

- Modelo local 7B/8B **não** segue 100% das instruções; desvios voltam a aparecer. Calibração é iterativa.
- Novas frases meta podem surgir; vale documentar aqui e acrescentar à lista de proibições no prompt ou no projeto.
- Qualidade da resposta depende do **retrieve** (relevância dos chunks) e do **conteúdo**; instruções sozinhas não compensam base fraca ou mal indexada.

**Biblioteca densa e respostas ainda fracas:** hoje já existe pelo menos um projeto com biblioteca **bem densa e retrabalhada** (redução de centenas de arquivos para dezenas, conteúdo consolidado e otimizado). Mesmo assim, as respostas e as consultas (retrieve + resposta da LLM) **não ficam tão boas** quanto o volume e a qualidade do conteúdo sugeririam. Ou seja: o gargalo não é só “pouco conteúdo” — é também o modelo (7B/8B) e a forma como o retrieve ranqueia e o modelo usa o contexto. Ter base forte ajuda, mas não basta; calibração e expectativa realista fazem parte do cenário.

---

## 6. Referências rápidas

| Onde | O quê |
|------|--------|
| `app/rag/prompt.py` | SYSTEM_TEMPLATE com calibração (resposta direta, proibições ampliadas, fallback curto, instrução anti-gramática). |
| `app/jobs/worker.py` | `_sanitize_answer()`: remoção de meta-frases no início, frase negativa longa, e "falecimento" em contexto de contato. |
| `app/jobs/worker.py` | `_rerank_for_diversity()`: limita a 2 chunks por documento para evitar redundância. |
| `app/registry.py` | `get_rag_policies()`: `max_chunk_distance` configurável por projeto (default 1.0). |
| `app/ingest/chunking.py` | Splitting por seções markdown (headings) antes de separator. |
| `app/ingest/indexer.py` | Metadata enriquecida (title, section) em cada chunk no Chroma. |
| Projeto (ex.: estudiosmobi) `fluxosLLM/instrucoes-llm.md` | Mood, proibições e tom por projeto. |
| 02-api-integration.md § 10 | Otimização de qualidade e instruções por projeto. |
| 02-api-integration.md § 13 | fluxosLLM e estudosmobi. |

---

## 7. Melhorias implementadas (março 2026)

### 7.1 Prompt base reforçado

**Desvio corrigido:** Meta-frases persistentes e gramática robótica.

**O que mudou em `app/rag/prompt.py`:**
- Lista de frases proibidas ampliada: adicionadas "Com base apenas na informação fornecida", "não há informações que justifiquem ou desaconselhem", "recomendo consultar os links", "De acordo com as informações disponíveis".
- Regra de fallback reescrita com exemplo concreto: "diga em UMA frase o que o serviço cobre e convide para contato".
- Instrução explícita anti-gramática: proíbe "Você pode abertura", "você pode fale".
- Nova regra para projetos de venda: tom de serviço, nunca soar negativo.

**Resultado esperado:** Menos meta-frases, fallback mais natural, tom mais assertivo.

### 7.2 Sanitização pós-processamento expandida

**Desvio corrigido:** Modelo 7B/8B ignora proibições do prompt ~20% das vezes.

**O que mudou em `app/jobs/worker.py`:**
- Nova função `_sanitize_answer()` centraliza todas as regras.
- Regra 1: remove prefixos meta ("Com base no contexto fornecido,", "Segundo o conteúdo,", etc.) via regex.
- Regra 2: remove frase longa negativa "Não encontrei informação suficiente na base de conhecimento..."
- Regra 3: "falecimento" → "fale conosco" (preservada da versão anterior, sem alteração).
- Todas as regras logam quando aplicadas.

**Resultado esperado:** Zero ocorrências das frases-alvo na resposta final.

### 7.3 MAX_CHUNK_DISTANCE configurável e reduzido

**Desvio corrigido:** Chunks com distance 1.0-1.2 (vagamente relacionados) poluíam o contexto e geravam respostas genéricas.

**O que mudou:**
- `app/registry.py`: novo campo `max_chunk_distance` em `get_rag_policies()`, default 1.0 (era 1.2 hardcoded).
- `app/jobs/worker.py`: usa `policies["max_chunk_distance"]` em vez de constante fixa.
- Projetos de venda podem usar 0.8-0.9 para filtragem mais agressiva.

**Resultado esperado:** Chunks entregues ao LLM são mais relevantes; menos respostas "fracas" por contexto poluído.

### 7.4 Re-ranking por diversidade

**Desvio corrigido:** Um único documento longo dominava os 5 chunks retornados, gerando respostas repetitivas.

**O que mudou em `app/jobs/worker.py`:**
- Nova função `_rerank_for_diversity()`: limita a 2 chunks por documento de origem (`path`).
- Chunks excedentes são movidos para o final (não descartados).
- Aplicada após `_filter_chunks_by_distance()`.

**Resultado esperado:** Respostas usam informação de múltiplas fontes; menos repetição.

### 7.5 Chunking por seção markdown

**Desvio corrigido:** Chunks cortavam no meio de uma seção temática, perdendo contexto.

**O que mudou em `app/ingest/chunking.py`:**
- Nova função `_split_by_sections()`: divide markdown por headings (##, ###) antes de aplicar split por tamanho.
- Heading preservado no início de cada chunk para contexto no retrieve.
- Fallback para split por separator quando não há headings.
- **Requer re-ingest** (`POST /ingest`) após deploy.

**Resultado esperado:** Chunks correspondem a seções temáticas; retrieve mais preciso.

### 7.6 Metadata enriquecida no ingest

**O que mudou em `app/ingest/indexer.py`:**
- Nova função `_extract_chunk_metadata()`: extrai `title` (da linha "Sobre:") e `section` (do heading) de cada chunk.
- Metadata armazenada no Chroma junto com `path`.
- **Requer re-ingest** após deploy.

**Resultado esperado:** Base para filtragem futura por título/seção no retrieve.

---

## 8. Guia de estrutura para arquivos .md na biblioteca

Para que o retrieve funcione bem e os chunks sejam autocontidos, os arquivos `.md` na biblioteca devem seguir este padrão:

### Estrutura recomendada

```markdown
# Título Claro e Descritivo do Tema

Resumo do tema em 2-3 frases. O que é, para quem serve, por que importa.
Este primeiro parágrafo vira o chunk mais importante no retrieve.

## Subtema 1

Conteúdo direto e objetivo sobre o subtema.
Evitar parágrafos longos — preferir listas e frases curtas.

## Subtema 2

Outro bloco temático autocontido.

## Contato / Como fazer

Informação prática: telefone, WhatsApp, link, passo a passo.
```

### Boas práticas

1. **Título (H1):** descritivo e com palavras-chave naturais. "Abertura de Empresa MEI" é melhor que "Serviço 1".
2. **Primeiro parágrafo:** resumo do tema. O ingest prepende "Sobre: {título}" automaticamente, mas o conteúdo do parágrafo é o que a LLM usa para responder.
3. **Seções (H2/H3):** cada seção vira um chunk separado (desde março 2026). Manter seções autocontidas — não depender de "como dito acima".
4. **Evitar tabelas complexas:** tabelas com muitas colunas são ruins para chunking e para a LLM. Preferir listas.
5. **Palavras-chave naturais:** incluir no texto, não como tags artificiais. "A Mobi faz abertura de empresa, alteração contratual e encerramento" é melhor que "tags: abertura, alteração, encerramento".
6. **Um tema por arquivo:** evitar arquivos "guarda-chuva" com 10 temas misturados. Melhor 5 arquivos curtos que 1 arquivo longo.
7. **Links externos:** incluir quando relevante (site, WhatsApp). A LLM pode citar links externos mas não cita caminhos internos.

---

## 9. Eval baseline (jun 2026)

Flags enabled on mini62 after sprint:

| Flag | Value |
|------|-------|
| `EMBEDDING_CACHE_ENABLED` | true |
| `RAG_HYBRID_ENABLED` | true |
| `RAG_RERANK_ENABLED` | true (enabled 2026-06-27; re-eval hit dedup — see below) |
| `RAG_REFLECTION_ENABLED` | false |

### Baseline recorded (2026-06-27, mini62)

| Project | Question | Result | Latency (hybrid only) | Latency (hybrid+rerank) |
|---------|----------|--------|----------------------|-------------------------|
| aiclaudia | Onde foi parar minha chave? | PASS | 27.9s | dedup (0.0s) |
| estudosmobi | Como abrir uma empresa MEI? | PASS | 17.7s | dedup (0.0s) |

### Eval pós-melhorias (2026-06-27)

Suite: `python3 scripts/eval_rag.py` com `tests/eval/eval_questions.json`.

| Project | Question | Critério |
|---------|----------|----------|
| aiclaudia | Qual é a capital da França? | PASS + `forbidden_keywords`: mobi, mobicontabil |
| aiclaudia | Onde foi parar minha chave? | PASS (creative, sem keywords) |
| estudosmobi | Como abrir uma empresa MEI? | PASS + keywords mei, empresa |
| bikeanjoall_2026 | O que é o Bike Anjo? | PASS + keywords voluntário/ciclismo |

Registar aqui hit-rate e latência após cada mudança de flags ou seed.

Flags active after sprint: hybrid + rerank + embedding cache. Re-ingest ran before first eval; a few estudosmobi chunks skipped on Ollama 500 during ingest. Second eval row reflects ask dedup, not rerank overhead — re-run with fresh questions to measure rerank latency.

Record hit-rate / latency here after each flag change.

Desde ago/2026 isto não precisa de ser transcrito à mão: `scripts/eval_rag.py` grava
cada corrida em `tests/eval/results/` com o `config_json` do projeto anexado, e
`--compare` imprime a tabela antes/depois já com o diff de configuração. A linha
"dedup (0.0s)" acima é o modo de falha que `--unique` evita — ver
[13 §2](./13-optimization-execution-plan.md).

---

**Anterior:** [06-edu-contract.md](./06-edu-contract.md) · **Seguinte:** [08-project-config.md](./08-project-config.md)
