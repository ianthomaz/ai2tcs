# 13 — Plano de Execução: Otimização Inteligente sem Quebra

> Objetivo: aplicar melhorias de alto impacto com baixo risco, preservando a utilização atual da API.

## Princípios

- **Simple is better**: mudanças pequenas, reversíveis e testáveis.
- **Respect previous code**: sem reestruturações grandes.
- **Compatibilidade primeiro**: comportamento atual permanece o padrão.
- **Placeholders**: não alterar placeholders existentes.

---

## Fase 1 (executável já, sem risco funcional)

### 1) Observabilidade mínima padronizada

Ação:
- Registrar em log por request: `request_id`, `path`, `status_code`, `duration_ms`.
- Manter payloads fora do log por padrão (segurança + LGPD).

Critério de pronto:
- É possível localizar requests lentos no log por `duration_ms`.

### 2) Baseline de performance e qualidade (controlado pelo time de produto)

Ação:
- Definir conjunto fixo de perguntas reais (amostra pequena, 20–30) com curadoria do time.
- Salvar baseline de latência e nota de qualidade manual.

Critério de pronto:
- Tabela "antes/depois" para qualquer mudança de RAG/modelo.

### 3) Feature flags para melhorias futuras

Ação:
- Guardar flags em `.env` para habilitar/desabilitar recursos sem deploy destrutivo:
  - `RAG_RERANK_ENABLED=false`
  - `RAG_HYBRID_ENABLED=false`
  - `RAG_REFLECTION_ENABLED=false`
  - `ASK_STREAM_ENABLED=false`
  - `EMBEDDING_CACHE_ENABLED=true`

Critério de pronto:
- Sistema atual continua igual com todas as flags em `false`.

---

## Fase 2 (alto impacto, risco controlado)

### 4) Reranker semântico (opt-in)

Ação:
- Inserir reranker após recuperação vetorial e antes da montagem do prompt.
- Começar com modelo leve.

Critério de pronto:
- Melhorar qualidade em amostra de perguntas sem piorar p95 de latência além do limite combinado.

### 5) Cache de embeddings da pergunta

Ação:
- Cache in-memory com limite de tamanho.
- TTL opcional em evolução posterior.

Critério de pronto:
- Reduzir latência média em perguntas repetidas.

### 6) Hybrid Search (BM25 + vetor)

Ação:
- Habilitar somente em projetos/rotas com termos exatos (NF, CNPJ, IDs).

Critério de pronto:
- Aumentar acerto em consultas com tokens exatos.

---

## Fase 3 (UX e escala)

### 7) Streaming de resposta (modo interativo)

Ação:
- Criar rota de streaming sem remover fluxo atual de jobs/polling.

Critério de pronto:
- Cliente interativo recebe tokens progressivos; integrações assíncronas continuam iguais.

### 8) Concorrência controlada de workers

Ação:
- Expor concorrência por config e subir gradualmente.

Critério de pronto:
- Mais throughput sem swap/degradação severa no host.

---

## Matriz risco x ganho

| Item | Ganho esperado | Risco | Ordem |
|---|---:|---:|---:|
| Observabilidade mínima | Alto | Baixo | 1 |
| Baseline de eval | Alto | Baixo | 2 |
| Feature flags | Médio | Baixo | 3 |
| Reranker | Alto | Médio | 4 |
| Cache embeddings | Médio | Baixo | 5 |
| Hybrid search | Médio | Médio | 6 |
| Streaming | Médio | Médio | 7 |
| Worker concurrency | Médio | Médio | 8 |

---

## Checklist operacional

- [ ] Criar baseline com 20–30 perguntas reais (curadoria manual do time)
- [ ] Definir limite de latência p95 por rota crítica
- [ x ] Ativar logs com `request_id` e `duration_ms`
- [ x ] Adicionar flags no `.env.example`
- [ ] Implementar reranker sob flag
- [ x ] Implementar cache sob flag
- [ x ] Implementar híbrido sob flag
- [ ] Validar regressão com testes + smoke

---

## Rollback padrão

Para qualquer feature nova:
1. Desabilitar flag no `.env`.
2. Reiniciar serviço.
3. Reexecutar smoke crítico.

Rollback deve ser possível em menos de 5 minutos.
