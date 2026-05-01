# LLM API — Roadmap de Upgrades e Melhorias Futuras

**Versão:** 1.0 (Marco/2026)
**Status:** Planejamento em progresso

---

## 📋 Visão Geral

Este documento lista todas as oportunidades de upgrade para o **LLM API** — tanto as em progresso quanto as planejadas para futuro. Divididas em **5 níveis**:

1. **Imediato** (1-2h) — Ajustes rápidos, impacto alto
2. **Curto Prazo** (2-4h) — Implementação simples, grande benefício
3. **Médio Prazo** (4-8h) — Requer refactoring moderado
4. **Longo Prazo** (1-2 dias) — Mudanças arquiteturais
5. **Futuro** (especulativo) — Pesquisa/exploração

---

## 🔴 CRÍTICO: Respostas Repetitivas (EM PROGRESSO)

### Problema Diagnosticado
- **Temperature 0.2** → Modelo demasiadamente conservador (determinístico)
- **Top-k 40** → Alto demais para 8B model; aumenta tokens repetidos
- **Repeat-penalty 1.1** → Insuficiente para combater repetição com temp tão baixa
- **Prompts genéricos** → Sem variação estrutural entre respostas

### Status: Implementando

#### ✅ Nível 1: Ajustes Imediatos de Parâmetros LLM

**O que fazer:**
- `temperature`: 0.2 → **0.5-0.6** (aumenta criatividade sem perder coerência)
- `top_k`: 40 → **25-30** (reduz tokens inadequados)
- `repeat_penalty`: 1.1 → **1.3-1.5** (penaliza repeats)

**Impacto esperado:** -60% repetição imediatamente

**Arquivos a modificar:**
- `app/jobs/worker.py` linha 112-117

**Commits necessários:**
1. Commit: "Increase LLM temperature to 0.5 and adjust top_k, repeat_penalty for more variety"

**Notas:**
- Sem risco: temperature 0.5 ainda mantém coerência em RAG
- Revisar respostas após ajuste
- Se muito criativa (hallucinations), reduzir para 0.45

---

#### ✅ Nível 2: Flexibilizar Parâmetros por Projeto

**O que fazer:**
1. Adicionar `llm_options` ao schema do projeto em `config_json`:
   ```json
   {
     "llm_options": {
       "temperature": 0.5,
       "top_k": 30,
       "top_p": 0.9,
       "repeat_penalty": 1.3,
       "num_predict": 1024
     }
   }
   ```

2. Criar função `get_llm_config()` em `app/registry.py`:
   ```python
   def get_llm_config(project: dict) -> dict:
       """Retorna config LLM do projeto, com fallbacks sensatos."""
       cfg = project.get("config_json") or {}
       if isinstance(cfg, dict):
           llm = cfg.get("llm_options") or {}
           return {
               "temperature": llm.get("temperature", 0.5),
               "top_k": llm.get("top_k", 30),
               "top_p": llm.get("top_p", 0.9),
               "repeat_penalty": llm.get("repeat_penalty", 1.3),
               "num_predict": llm.get("num_predict", 1024),
           }
       return {
           "temperature": 0.5,
           "top_k": 30,
           "top_p": 0.9,
           "repeat_penalty": 1.3,
           "num_predict": 1024,
       }
   ```

3. Usar em `app/jobs/worker.py`:
   ```python
   llm_config = get_llm_config(project)
   response = await asyncio.to_thread(
       ollama.chat,
       model=OLLAMA_MODEL,
       messages=[...],
       options=llm_config,
   )
   ```

**Impacto esperado:** Permiti controle fino por projeto (ex: "creative" vs "conservative")

**Arquivos a modificar:**
- `app/registry.py` (adicionar função)
- `app/jobs/worker.py` (usar função)
- Documentação (`MANUAL_INTEGRACAO.md`)

**Commits necessários:**
1. "Add get_llm_config() to registry.py with flexible LLM parameters"
2. "Update worker.py to use configurable LLM options per project"

---

#### 🟡 Nível 3: Variação no System Prompt (PLANEJADO)

**O que fazer:**
1. Detectar tipo de pergunta:
   - Técnica/documental (dados, HOW-TO)
   - Conversacional (bate-papo, contexto pessoal)
   - Pessoal/emocional

2. Variar `system_prompt` conforme tipo:
   ```
   Se técnica:
     "Seja conciso, cite fontes, use estrutura (bullets/tabelas)"

   Se conversacional:
     "Seja amigável, mantenha tom informal, use histórico"

   Se pessoal:
     "Considere contexto pessoal do usuário, mostre empatia"
   ```

3. Em `app/rag/prompt.py`:
   ```python
   def _detect_question_type(question: str, history: list) -> str:
       # Lógica simples de detecção
       if len(history) > 0:
           return "conversational"
       if any(keyword in question.lower() for keyword in ["como", "tutorial", "passo"]):
           return "technical"
       return "general"

   def build_messages(...):
       q_type = _detect_question_type(question, conversation_history)
       system_msg = SYSTEM_TEMPLATES[q_type].format(...)
   ```

**Impacto esperado:** +40% variação nas respostas, melhor adaptação ao tipo de pergunta

**Status:** Design pronto, implementação em backlog

---

#### 🟡 Nível 4: Diversidade de Chunks (RE-RANKING)

**O que fazer:**
1. Após retrieval, aplicar **re-ranking com diversidade**:
   - Recuperar top-k chunks normalmente
   - Descartar chunks muito similares entre si
   - Selecionar top-n com máxima divergência temática

2. Em `app/rag/retrieve.py`:
   ```python
   def _diversity_rerank(chunks: list[dict], max_chunks: int = 5) -> list[dict]:
       """Seleciona chunks com máxima divergência."""
       if len(chunks) <= max_chunks:
           return chunks

       selected = [chunks[0]]
       for chunk in chunks[1:]:
           if len(selected) >= max_chunks:
               break
           # Calcular dissimilaridade com chunks já selecionados
           if _is_diverse_from(chunk, selected):
               selected.append(chunk)
       return selected
   ```

**Impacto esperado:** +30% variação contexto RAG, reduz redundância

**Status:** Prototipado, pronto para implementação

---

### 🟠 Nível 5: Feedback de Usuário → Auto-Ajuste (MÉDIO PRAZO)

**O que fazer:**
1. Adicionar campo ao job: `user_satisfaction` (0-1.0)
   - Via endpoint: `PUT /jobs/{job_id}/feedback`
   - Payload: `{"satisfaction": 0.7, "reason": "repetitive"}`

2. Armazenar feedback no PostgreSQL

3. Auto-ajuste automático:
   - Se feedback < 0.5 em últimas 3 respostas: aumentar temperature
   - Se feedback > 0.9: manter estável
   - Se > 0.9 + muitos hallucinations: reduzir temperature

4. Endpoint novo:
   ```python
   PUT /jobs/{job_id}/feedback
   {
     "satisfaction": 0.4,
     "reason": "repetitive | not_relevant | hallucination | good"
   }
   ```

**Impacto esperado:** Melhoria contínua automática por projeto

**Arquivos a modificar:**
- `app/db.py` (adicionar coluna `feedback_satisfaction` em Job)
- `app/api/main.py` (novo endpoint)
- `app/jobs/worker.py` (lógica de auto-ajuste)

**Commits necessários:** 3-4 commits

**Status:** Design completo, em backlog

---

## 📚 Documentação e Onboarding (EM PROGRESSO)

### ✅ Nível 1: Reorganizar Manual de Integração

**Status:** Planning
- Consolidar e limpar `MANUAL_INTEGRACAO.md`
- Adicionar índice (table of contents) visual
- Reorganizar seções por ordem de relevância
- Separar "getting started" de "advanced"

**O que fazer:**
1. Criar `docs/GUIA_RAPIDO.md` (5min reading)
   - Setup básico
   - Primeiro `/ask`
   - Polling pattern

2. Refatorar `MANUAL_INTEGRACAO.md`
   - § 1-3: Setup e autenticação (MOVE para o topo)
   - § 4-7: Endpoints principais e exemplos
   - § 8-13: Integração por linguagem, troubleshooting

3. Consolidar `docs/OPERACAO_TAILSCALE.md` em apêndice

**Impacto esperado:** 30% menos tempo de onboarding para novos projetos

---

### ✅ Nível 2: Criar DEVELOPER_GUIDE.md

**Status:** Implementation ready (ver arquivo separado)

**O que fazer:**
- Guia de como estender a API
- Padrões de código
- Como adicionar novos endpoints
- Como testar localmente
- Troubleshooting para devs

**Arquivos a criar:**
- `docs/DEVELOPER_GUIDE.md`

**Impacto esperado:** Comunidade pode contribuir, manutenção facilitada

---

### 🟡 Nível 3: Documentar Configuração por Projeto

**Status:** Em progresso

**O que fazer:**
1. Criar `docs/PROJECT_CONFIG.md`
   - Exemplo de `config_json` completo
   - Explicar cada opção
   - Templates para projetos comuns

2. Exemplos:
   ```json
   {
     "bikeanjoall_2026": {
       "chunking": { "chunk_size": 512, "chunk_overlap": 64 },
       "llm_options": { "temperature": 0.5, "top_k": 30 },
       "policies": { "max_chunks_to_retrieve": 5 }
     },
     "creative_content": {
       "llm_options": { "temperature": 0.8, "repeat_penalty": 1.5 }
     },
     "legal_docs": {
       "llm_options": { "temperature": 0.2, "repeat_penalty": 2.0 }
     }
   }
   ```

**Impacto esperado:** Cada projeto pode otimizar seus parâmetros facilmente

---

## 🎯 Melhorias Gerais (FUTURO)

### Qualidade de Resposta

| ID | Upgrade | Dificuldade | Benefício | Status |
|----|---------|-------------|----------|--------|
| QA-01 | Aumentar contexto window (embeddings menores) | 🟡 | +30% acurácia em RAG | Backlog |
| QA-02 | Fine-tuning em dataset de QA Bike Anjo | 🔴 | +50% acurácia domínio | Futuro |
| QA-03 | Fact-checking automático (verificar sources) | 🟡 | -90% hallucinations | Backlog |
| QA-04 | Multi-step reasoning (chain-of-thought) | 🟠 | +40% respostas complexas | Backlog |
| QA-05 | Embedding hybrid (BM25 + semantic) | 🟠 | +20% recall | Pesquisa |

### Conversação e Contexto

| ID | Upgrade | Dificuldade | Benefício | Status |
|----|---------|-------------|----------|--------|
| CV-01 | Aumentar janela de histórico (10→20 msgs) | ✅ | +25% coesão conversa | Imediato |
| CV-02 | Tópico-tracking automático (mudança de assunto) | 🟠 | +30% relevância | Backlog |
| CV-03 | Intent detection (pergunta vs feedback vs comando) | 🟡 | +Roteamento automático | Backlog |
| CV-04 | Personalization baseado em história longa | 🟡 | +50% satisfação | Backlog |
| CV-05 | Multi-turn clarifications ("quer dizer...?") | 🟠 | +Fluidez | Pesquisa |

### Performance e Escalabilidade

| ID | Upgrade | Dificuldade | Benefício | Status |
|----|---------|-------------|----------|--------|
| PF-01 | Cache de embeddings (reduce Ollama calls) | 🟡 | -40% latência | Backlog |
| PF-02 | Batch inference (multiple questions) | 🟠 | -30% latência bulk | Backlog |
| PF-03 | Streaming responses (SSE) | 🟠 | +UX (vê resposta em tempo real) | Backlog |
| PF-04 | Model quantization (llama2:7b-q4 vs 8b) | 🟡 | -50% memory, -10% quality | Pesquisa |
| PF-05 | Índice vetorial distributed (Milvus/Weaviate) | 🔴 | +1000x escalabilidade | Futuro |

### Novos Recursos

| ID | Upgrade | Dificuldade | Benefício | Status |
|----|---------|-------------|----------|--------|
| FR-01 | Geração automática de FAQ (from conversations) | 🟠 | Manutenção semiautomática de docs | Backlog |
| FR-02 | Análise de gaps (perguntas sem resposta) | 🟡 | Identifica conteúdo faltante | Backlog |
| FR-03 | Multi-language support (não só PT) | 🟠 | +3 idiomas | Pesquisa |
| FR-04 | Image understanding (para flowmaps visual) | 🔴 | LLaVA or Clip | Futuro |
| FR-05 | Citation verification (com links) | 🟡 | Links diretos ao source | Backlog |

### Integração com Externos

| ID | Upgrade | Dificuldade | Benefício | Status |
|----|---------|-------------|----------|--------|
| EX-01 | Fetch conteúdo from URLs (not just local) | 🟡 | Integra docs online | Backlog |
| EX-02 | Database direct query (vs RAG only) | 🔴 | Dados real-time | Futuro |
| EX-03 | Webhook para projetos notificarem updates | 🟡 | Auto-reindex | Backlog |
| EX-04 | GraphQL API (além de REST) | 🟠 | +Flexibilidade queries | Pesquisa |
| EX-05 | OpenAI API compatibility | 🟡 | Drop-in replacement | Backlog |

---

## 📊 Roadmap Timeline

```
Março 2026
  └─ ✅ Nível 1: Temperature + top_k + repeat_penalty
     ✅ Nível 2: get_llm_config() (flexibilizar por projeto)
     ✅ Documentação: UPGRADES.md + DEVELOPER_GUIDE.md

Abril 2026 (Planejado)
  └─ 🟡 Nível 3: Variação system prompt
     🟡 Limpeza manual integração
     🟡 PROJECT_CONFIG.md

Maio 2026 (Planejado)
  └─ 🟠 Nível 4: Diversity re-ranking
     🟠 Limpeza conversation summaries

Junho 2026 (Planejado)
  └─ 🔴 Nível 5: Feedback loop + auto-ajuste
     🟡 Fine-tuning para domínio específico

```

---

## 🚀 Como Usar Este Documento

1. **Dev fazendo upgrade?** → Veja seção correspondente, execute checklist
2. **Planejando feature?** → Busque na tabela "Melhorias Gerais"
3. **Encontrou bug?** → Abra issue com `[BUG]` no título
4. **Tem ideia?** → Adicione linha nova na tabela apropriada

---

## Chaves por projeto, gateway Tailscale e reintegração (planejado)

**Status:** planejamento ativo (abril/2026).

Notas detalhadas, checklist de entregas e perguntas para fechar o desenho: [docs/PLANO_CHAVES_ROTEADOR_REINTEGRACAO.md](docs/PLANO_CHAVES_ROTEADOR_REINTEGRACAO.md).

---

## 📝 Histórico de Mudanças

| Versão | Data | Descrição |
|--------|------|-----------|
| 1.0 | Março/2026 | Documento inicial; planejamento completo |
| 1.1 | Abril/2026 | Referência ao plano de chaves, roteador Tailscale e manual de reintegração |

---

## ❓ Perguntas? Dúvidas?

Veja `DEVELOPER_GUIDE.md` para padrões de código, ou contacte `@ianthomaz` no repositório.
