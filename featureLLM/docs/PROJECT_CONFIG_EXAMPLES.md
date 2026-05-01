# Exemplos de Configuração de Projetos

Como configurar diferentes tipos de projetos com parâmetros otimizados.

---

## 📋 Índice

1. [Projeto de Comunidade (Bike Anjo)](#bike-anjo)
2. [Projeto Técnico/Legal](#técnico)
3. [Projeto de Suporte/FAQ](#faq)
4. [Projeto Criativo/Marketing](#criativo)
5. [Template Customizado](#customizado)

---

## Bike Anjo

**Características:** Comunidade de ciclismo, perguntas variadas, precisa de contexto pessoal

**Configuração otimizada:**

```json
{
  "project_id": "bikeanjoall_2026",
  "name": "Bike Anjo",
  "sources": [
    "/caminho/para/bikeanjo/bibliotecaConteudoLLM",
    "/caminho/para/bikeanjo/mapaFluxosLLM"
  ],
  "config_json": {
    "chunking": {
      "chunk_size": 512,
      "chunk_overlap": 64,
      "separator": "\n\n"
    },
    "embedding_model": "nomic-embed-text",
    "policies": {
      "prefer_cite_sources": true,
      "when_no_answer": "no_answer",
      "max_chunks_to_retrieve": 5
    },
    "llm_options": {
      "temperature": 0.5,
      "top_k": 30,
      "top_p": 0.9,
      "repeat_penalty": 1.3,
      "num_predict": 1024
    }
  },
  "themes": [
    "rotas",
    "segurança",
    "voluntariado",
    "manutenção",
    "saúde"
  ]
}
```

**Por que estes valores:**
- `temperature: 0.5` — Equilíbrio entre criatividade (responder variadas) e coerência
- `top_k: 30` — Evita tokens aleatórios demais
- `max_chunks_to_retrieve: 5` — Informação suficiente sem poluir contexto
- `chunk_size: 512` — Bom para FAQ + docs estruturados

---

## Projeto Técnico/Legal

**Características:** Respostas precisas, nunca inventar, citações obrigatórias

**Configuração otimizada:**

```json
{
  "project_id": "legal_docs_2026",
  "name": "Documentação Jurídica",
  "sources": [
    "/caminho/para/legal/docs",
    "/caminho/para/legal/templates"
  ],
  "config_json": {
    "chunking": {
      "chunk_size": 768,
      "chunk_overlap": 128,
      "separator": "\n\n"
    },
    "embedding_model": "nomic-embed-text",
    "policies": {
      "prefer_cite_sources": true,
      "when_no_answer": "no_answer",
      "max_chunks_to_retrieve": 7
    },
    "llm_options": {
      "temperature": 0.2,
      "top_k": 25,
      "top_p": 0.8,
      "repeat_penalty": 1.5,
      "num_predict": 1024
    }
  },
  "themes": [
    "contrato",
    "regulatória",
    "compliance",
    "estrutura"
  ]
}
```

**Por que estes valores:**
- `temperature: 0.2` — Muito conservador, prioriza exatidão
- `top_k: 25` — Baixo para evitar alucinações
- `max_chunks_to_retrieve: 7` — Contexto completo é importante
- `repeat_penalty: 1.5` — Alto para evitar padrões repetidos
- `chunk_size: 768` — Chunks maiores para docs longos

---

## Projeto de Suporte/FAQ

**Características:** Muitas perguntas similares, respostas rápidas esperadas

**Configuração otimizada:**

```json
{
  "project_id": "support_faq_2026",
  "name": "Suporte Técnico",
  "sources": [
    "/caminho/para/support/faq",
    "/caminho/para/support/troubleshooting"
  ],
  "config_json": {
    "chunking": {
      "chunk_size": 256,
      "chunk_overlap": 32,
      "separator": "\n\n"
    },
    "embedding_model": "nomic-embed-text",
    "policies": {
      "prefer_cite_sources": true,
      "when_no_answer": "need_more_info",
      "max_chunks_to_retrieve": 3
    },
    "llm_options": {
      "temperature": 0.4,
      "top_k": 28,
      "top_p": 0.85,
      "repeat_penalty": 1.2,
      "num_predict": 512
    }
  },
  "themes": [
    "instalação",
    "erro",
    "performance",
    "troubleshooting"
  ]
}
```

**Por que estes valores:**
- `temperature: 0.4` — Moderado, permite um pouco de variação
- `chunk_size: 256` — Pequeno para FAQs atomizadas
- `max_chunks_to_retrieve: 3` — FAQ direto, sem contexto desnecessário
- `num_predict: 512` — Respostas mais curtas esperadas

---

## Projeto Criativo/Marketing

**Características:** Respostas diferenciadas, tom variado, menos formal

**Configuração otimizada:**

```json
{
  "project_id": "marketing_content_2026",
  "name": "Conteúdo Marketing",
  "sources": [
    "/caminho/para/marketing/blog",
    "/caminho/para/marketing/campanha"
  ],
  "config_json": {
    "chunking": {
      "chunk_size": 512,
      "chunk_overlap": 64,
      "separator": "\n\n"
    },
    "embedding_model": "nomic-embed-text",
    "policies": {
      "prefer_cite_sources": false,
      "when_no_answer": "need_more_info",
      "max_chunks_to_retrieve": 4
    },
    "llm_options": {
      "temperature": 0.7,
      "top_k": 35,
      "top_p": 0.95,
      "repeat_penalty": 1.1,
      "num_predict": 1024
    }
  },
  "themes": [
    "brand",
    "conteúdo",
    "campanha",
    "tom"
  ]
}
```

**Por que estes valores:**
- `temperature: 0.7` — Alto, para variedade e criatividade
- `top_k: 35` — Maior diversidade de tokens
- `top_p: 0.95` — Nucleus sampling muito aberto
- `prefer_cite_sources: false` — Não precisa citar sempre
- `repeat_penalty: 1.1` — Baixo, permite mais liberdade

---

## Template Customizado

Use este template para criar seu próprio projeto:

```json
{
  "project_id": "meu_projeto_2026",
  "name": "Meu Projeto",
  "sources": [
    "/caminho/para/meu/conteudo",
    "/caminho/para/meu/fluxos"
  ],
  "config_json": {
    "chunking": {
      "chunk_size": 512,          # 256: pequeno (FAQ), 512: médio, 768: grande (docs longos)
      "chunk_overlap": 64,        # Sobreposição: 32 (pequeno), 64 (médio), 128 (grande)
      "separator": "\n\n"         # Separador de chunks
    },
    "embedding_model": "nomic-embed-text",  # Mantém padrão
    "policies": {
      "prefer_cite_sources": true,           # Sempre citar sources?
      "when_no_answer": "no_answer",         # "no_answer" ou "need_more_info"
      "max_chunks_to_retrieve": 5            # 3-7, mais = mais contexto
    },
    "llm_options": {
      "temperature": 0.5,                    # 0.2: preciso, 0.5: equilibrio, 0.7+: criativo
      "top_k": 30,                           # 25-35, menor = menos aleatório
      "top_p": 0.9,                          # 0.8-0.95, maior = mais criativo
      "repeat_penalty": 1.3,                 # 1.1-2.0, maior = penaliza repeats
      "num_predict": 1024                    # Tamanho max da resposta (tokens)
    }
  },
  "themes": [
    "tema1",
    "tema2"
  ]
}
```

---

## Projeto de Venda/Serviços (ex.: estudosmobi)

**Características:** Tom de serviço, direcionar para contato, nunca soar negativo, respostas assertivas

**Configuração otimizada:**

```json
{
  "project_id": "estudosmobi_2026",
  "name": "Estudos Mobi",
  "sources": [
    "/caminho/para/estudosmobi/bibliotecaConteudoLLM",
    "/caminho/para/estudosmobi/mapaFluxosLLM"
  ],
  "config_json": {
    "chunking": {
      "chunk_size": 512,
      "chunk_overlap": 64,
      "separator": "\n\n"
    },
    "embedding_model": "nomic-embed-text",
    "policies": {
      "prefer_cite_sources": true,
      "when_no_answer": "no_answer",
      "max_chunks_to_retrieve": 5,
      "max_chunk_distance": 0.9
    },
    "llm_options": {
      "temperature": 0.3,
      "top_k": 25,
      "top_p": 0.85,
      "repeat_penalty": 1.4,
      "num_predict": 1024
    },
    "behavior_instruction_path": "instrucoes-llm.md"
  },
  "themes": [
    "contabilidade",
    "abertura",
    "mei",
    "alteração",
    "impostos"
  ]
}
```

**Por que estes valores:**
- `temperature: 0.3` — Baixa para respostas focadas e sem divagação; em projetos de venda, consistência > criatividade
- `top_k: 25` — Conservador para evitar tokens inesperados
- `repeat_penalty: 1.4` — Evita repetições sem prejudicar coerência
- `max_chunk_distance: 0.9` — Mais restritivo que o padrão (1.2); filtra chunks vagamente relacionados que poluem o contexto e geram respostas fracas
- `behavior_instruction_path` — Arquivo com mood de venda e proibições específicas do projeto

**Nota sobre calibração:** Projetos de venda/serviços tendem a sofrer mais com meta-frases e tom neutro da LLM. Além dos params acima, é essencial ter um `instrucoes-llm.md` com regras de tom e proibições. Ver [CALIBRACAO_LLM.md](./CALIBRACAO_LLM.md) para desvios conhecidos.

---

## Selecionando Parâmetros

### Temperature (Criatividade)

| Valor | Uso | Característica |
|-------|-----|-----------------|
| 0.1-0.3 | Legal, Técnico | Deterministico, preciso, sem variação |
| 0.4-0.6 | Geral, Suporte | Equilíbrio, algumas variações |
| 0.7-0.9 | Marketing, Criativo | Muito criativo, mais alucinações |

### Top-K (Diversidade de Tokens)

| Valor | Uso |
|-------|-----|
| 20-25 | Muito conservador, evita alucinações |
| 28-32 | Padrão, bom balanço |
| 35-40 | Criativo, mais variação (risco > hallucination) |

### Repeat Penalty (Penalização de Repetição)

| Valor | Uso |
|-------|-----|
| 1.0-1.1 | Permitir repeats (rare) |
| 1.2-1.4 | Padrão, penaliza levemente |
| 1.5-2.0 | Muito agressivo contra repeats (pode prejudicar coerência) |

### Max Chunks to Retrieve (Informação)

| Valor | Uso |
|-------|-----|
| 3 | Resposta rápida, FAQ direto |
| 5 | Padrão, bom contexto |
| 7+ | Resposta detalhada, docs complexas |

---

## 📊 Benchmark: Tempo de Resposta

Com `llama3:8b` local, tempo médio (percentis):

| Tipo | P50 | P95 | P99 |
|------|-----|-----|-----|
| **FAQ** (3 chunks, 256 size) | 12s | 25s | 40s |
| **Padrão** (5 chunks, 512 size) | 25s | 45s | 60s |
| **Completo** (7 chunks, 768 size) | 40s | 70s | 90s |

Se respostas > 60s, considere reduzir:
- `max_chunks_to_retrieve` (de 5 para 3)
- `chunk_size` (de 512 para 256)

---

## 🔄 Como Atualizar Configuração

### Via SQL (direto)

```sql
UPDATE "Project"
SET config_json = jsonb_set(
  config_json,
  '{llm_options,temperature}',
  '0.6'::jsonb
)
WHERE project_id = 'bikeanjoall_2026';
```

### Via API

```bash
curl -X PUT http://127.0.0.1:28471/projects/bikeanjoall_2026 \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_json": {
      "llm_options": {
        "temperature": 0.6,
        "top_k": 30
      }
    }
  }'
```

### Via código

```python
from app import db as db_module

async def update_project_config():
    await db_module.execute("""
    UPDATE "Project"
    SET config_json = jsonb_set(
      config_json,
      '{llm_options,temperature}',
      '0.6'::jsonb
    )
    WHERE project_id = $1
    """, 'bikeanjoall_2026')
```

---

## Instrução de comportamento (contexto vendedor)

Para projetos em que o usuário pode ser **vendedor/parceiro** (ex.: estudiosmobi), use um arquivo no repositório do projeto e referencie no `config_json`:

**1. Crie no projeto** (ex.: `bibliotecaConteudoLLM/instrucoes-llm.md`):

```markdown
O usuário pode ser um vendedor ou parceiro. Adapte a resposta para quem vai indicar ou vender o serviço: destaque argumentos de venda e benefícios, sempre com base no contexto.
```

**2. No banco (config_json do projeto):**

```json
{
  "behavior_instruction_path": "instrucoes-llm.md"
}
```

O caminho é relativo à **primeira pasta** em `sources`. Alternativa: use `"system_instruction": "texto aqui"` no `config_json` para definir a instrução direto no banco (sem arquivo).

Para desvios comuns da LLM (frases meta, autodesvalorização, tom) e o que já está calibrado no prompt base, ver [CALIBRACAO_LLM.md](./CALIBRACAO_LLM.md).

---

## 🚀 Dicas para Otimizar

1. **Começar com defaults** (`temperature: 0.5`)
2. **Testar com perguntas reais** do projeto
3. **Medir satisfação** (feedback de usuários)
4. **Ajustar incrementalmente** (±0.1 na temperature)
5. **Reindexar após mudanças** em sources: `POST /ingest`

---

**Precisa de ajuda?** Veja [DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md) ou abra issue no repositório **ai2tcs** no GitHub.
