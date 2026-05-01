# Upgrade de Modelo LLM — Análise e Proposta

**Data:** Março 2026  
**Contexto:** Mac mini M4, 32GB RAM unificada.

**Decisão (Mar/2026):** Migrado para `qwen2.5:14b-instruct`. Configurável via `OLLAMA_CHAT_MODEL` no `.env`. Indexação permanece — embeddings são independentes do modelo de chat.

### O que fazer agora (no mini)
1. `ollama pull qwen2.5:14b-instruct` — baixar o modelo
2. Reiniciar a API (`./scripts/run_api.sh` ou launchd)
3. (Opcional) Se quiser outro modelo: `OLLAMA_CHAT_MODEL=outro-modelo` no `.env`

**Indexação:** Não precisa re-indexar. Os embeddings (nomic-embed-text) e o Chroma permanecem; só o modelo que gera a resposta mudou.

---

## Modelo leve para router e summary — implementado

**Implementação (Mar/2026):** Dual LLM Strategy via `OLLAMA_FAST_MODEL` e `OLLAMA_SMART_MODEL`.

| Fluxo | Modelo default | Aliases |
|-------|----------------|---------|
| Router (`/router`) | fast (llama3:8b) | `model: fast` ou `smart` no body |
| Summary (maintenance) | fast (llama3:8b) | — |
| Extract (onboarding) | fast (llama3:8b) | — |
| RAG (`/ask`) | smart (qwen2.5:14b-instruct) | `model` em user_context |
| NF extract | smart (qwen2.5:14b-instruct) | `model` em form |

**Status:** [ x ] Implementado. Ver `settings.get_model_name()` e testes em `tests/test_dual_llm.py`.

---

## 1. Situação Atual

### Modelo em uso
- **Padrão:** `qwen2.5:14b-instruct` (config.py; override via `OLLAMA_CHAT_MODEL`)
- **Fluxos que usam LLM:**

| Fluxo | Arquivo | Uso |
|-------|---------|-----|
| RAG /ask (respostas com base na biblioteca) | `worker.py` | Principal; maior impacto em qualidade |
| Roteamento de intenção (zapzap) | `message_router.py` | Router: ask vs cadastro vs escalar, etc. |
| Extração NF (enriquecimento) | `nf_extract.py` | JSON de campos de nota fiscal |
| Extração zapzap (onboarding) | `extract.py` | interesse, nome, cpf, email, etc. |
| Manutenção de conversas | `conversation_maintenance.py` | Resumos de mensagens antigas |
| (ExtratNFdata standalone) | `ExtratNFdata/` | Mesmo conceito, outro projeto |

### Parâmetros já configuráveis por projeto (`llm_options`)
- `temperature`, `top_k`, `top_p`, `repeat_penalty`, `num_predict`
- `tone_of_voice`, `message_size` (usados no prompt, não passados ao Ollama)
- **Não existe hoje:** escolha de modelo por projeto ou por fluxo.

---

## 2. Hardware: O que o mini 32GB suporta

| Modelo | RAM aproximada | Viável no mini 32GB? |
|--------|----------------|----------------------|
| 8B Q4 | ~5–6 GB | [x] Sim, folga |
| 12B Q4 (Mistral Nemo) | ~8 GB | [x] Sim |
| 13B Q4 | ~8–9 GB | [x] Sim |
| 14B Q4 (Qwen2.5, Gemma) | ~10 GB | [x] Sim, com cuidado em multitarefa |
| 70B Q4 | ~40–48 GB | [ ] Não; precisaria de swap intenso e seria lento |

**Conclusão:** 13B, 12B ou 14B quantizados são realistas. 70B não vale a pena em 32GB.

---

## 3. Alternativas de modelo (Ollama)

### 3.1 Mantendo 8B — upgrade mínimo
| Modelo | Notas |
|--------|-------|
| `llama3.1:8b-instruct` | Melhor que 3.2:8b em seguir instruções (conforme mensagem recebida) |
| `llama3.1:8b-instruct-q4_0` | Quantizado; mais rápido, mesma footprint |

### 3.2 Salto para 12–14B
| Modelo | Notas |
|--------|-------|
| `mistral-nemo:12b-instruct-2407` | Bom meio-termo; segue instruções bem |
| `qwen2.5:14b-instruct-q4_0` | 14B, bom em instruções e raciocínio |
| `llama3.1:8b-instruct` | Se preferir manter 8B com melhor qualidade |

### 3.3 Sugestão de ordem de teste
1. **Fase 1:** `llama3.1:8b-instruct` — troca direta, sem mudar memória.
2. **Fase 2:** `mistral-nemo:12b-instruct-2407` — testar salto de qualidade.
3. **Fase 3:** `qwen2.5:14b-instruct-q4_0` — se 12B rodar bem e quiser mais capacidade.

---

## 4. Impacto nos fluxos de API — Checklist de mudanças

### 4.1 Onde o modelo é usado (resumo)

| Componente | Atual | Possível mudança |
|------------|-------|------------------|
| `worker.py` | `OLLAMA_MODEL` fixo | Usar modelo de `config` ou `llm_options.model` |
| `message_router.py` | `OLLAMA_MODEL` fixo | Idem |
| `nf_extract.py` | `OLLAMA_MODEL` fixo | Idem ou parâmetro opcional |
| `extract.py` | `OLLAMA_MODEL` fixo | Idem |
| `conversation_maintenance.py` | `SUMMARY_MODEL` fixo | Pode continuar com modelo leve (velocidade) |

### 4.2 Opções de arquitetura

**Opção A — Modelo global (mais simples)**  
- Uma variável de ambiente: `OLLAMA_CHAT_MODEL=llama3.1:8b-instruct`
- Usada em todos os fluxos; um único ponto de configuração.
- **Prós:** Mudança mínima, rollout rápido.  
- **Contras:** Todos os fluxos usam o mesmo modelo.

**Opção B — Modelo global + override por projeto**  
- `OLLAMA_CHAT_MODEL` como default.
- `config_json.llm_options.model` como override por projeto.
- **Prós:** Flexibilidade (ex.: um projeto mais pesado em 12B, outro em 8B).  
- **Contras:** Mais lógica e documentação.

**Opção C — Modelo por tipo de fluxo**  
- `chat_model` (RAG), `router_model`, `extract_model`, `summary_model`.  
- **Prós:** Router e summary podem usar modelo mais leve.  
- **Contras:** Muitas variáveis, mais complexo.

### 4.3 Recomendação

- **Curto prazo:** Opção A — variável `OLLAMA_CHAT_MODEL` em `config.py`, usada em todos os fluxos.
- **Médio prazo:** Adicionar Opção B — `llm_options.model` opcional por projeto.

---

## 5. Mudanças necessárias (det声明)

### 5.1 Arquivos a alterar

| Arquivo | Mudança |
|---------|---------|
| `app/config.py` | Adicionar `ollama_chat_model: str = "llama3:8b"` (com fallback para env `OLLAMA_CHAT_MODEL`) |
| `app/jobs/worker.py` | Trocar `OLLAMA_MODEL` por `settings.ollama_chat_model` (ou `get_llm_model(project)`) |
| `app/api/message_router.py` | Idem |
| `app/api/nf_extract.py` | Idem |
| `app/api/extract.py` | Idem |
| `app/jobs/conversation_maintenance.py` | Usar `settings.ollama_chat_model` ou manter `SUMMARY_MODEL` separado |
| [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md) | Documentar `OLLAMA_CHAT_MODEL` |
| [PROJECT_CONFIG_EXAMPLES.md](./PROJECT_CONFIG_EXAMPLES.md) | Se implementar override por projeto |

### 5.2 API REST — impacto em contratos

| Endpoint | Mudança no contrato? |
|----------|----------------------|
| `POST /ask` | [ ] Não — modelo vem do servidor/projeto |
| `GET /status/{id}`, `GET /result/{id}` | [ ] Não |
| `POST /router` | [ ] Não |
| `POST /nfExtract` | [ ] Opcional — parâmetro `model` em form (override pontual) |
| `POST /extract`, `POST /extract-multi` | [ ] Opcional — idem |

**Resumo:** Nenhuma mudança obrigatória no contrato da API. Clientes atuais continuam funcionando.

### 5.3 Parâmetros novos (Ollama) — se quiser explorar

| Parâmetro | Descrição | Já suportado? |
|-----------|-----------|---------------|
| `num_ctx` | Tamanho do contexto (ex.: 4096, 8192) | [ ] Não usado hoje |
| `top_p` | Já em `llm_options` | [x] Sim |
| `mirostat` | Alternativa a temp/top_p para controle de perplexidade | [ ] Não |

`num_ctx` pode ser útil para 12B/14B com contextos maiores. Podemos adicionar em `llm_options` quando fizer sentido.

---

## 6. Plano de execução sugerido

### Fase 1 — Troca de modelo (Opção A)
1. Adicionar `OLLAMA_CHAT_MODEL` em `config.py`.
2. Centralizar uso em `worker`, `message_router`, `nf_extract`, `extract`, `conversation_maintenance`.
3. Rodar `ollama pull llama3.1:8b-instruct` no mini.
4. Ajustar `.env`: `OLLAMA_CHAT_MODEL=llama3.1:8b-instruct`.
5. Testar fluxos principais (ask, router, nfExtract, extract).
6. Documentar em [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md).

### Fase 2 — Teste de 12B (opcional)
1. `ollama pull mistral-nemo:12b-instruct-2407`.
2. Testar manualmente no mini (memória, latência).
3. Se estável: `OLLAMA_CHAT_MODEL=mistral-nemo:12b-instruct-2407` e novo ciclo de testes.

### Fase 3 — Override por projeto (opcional)
1. Adicionar `model` em `get_llm_config()` (registry).
2. Se `llm_options.model` existir, usar; senão, `settings.ollama_chat_model`.
3. Documentar em [PROJECT_CONFIG_EXAMPLES.md](./PROJECT_CONFIG_EXAMPLES.md).

---

## 7. Checklist antes de mudar

- [ ] Decidir modelo alvo (llama3.1:8b vs mistral-nemo:12b).
- [ ] Decidir arquitetura (só global vs global + override por projeto).
- [ ] Confirmar que `ollama pull <modelo>` funciona no mini.
- [ ] Fazer backup/config snapshot antes de trocar .env.
- [ ] Comunicar clientes (zapzap, webplacecc, etc.) se houver mudança de latência esperada.

---

## 8. Referências

- Planejamento: [00_PLANEJAMENTO_LLM_LOCAL.md](../00_PLANEJAMENTO_LLM_LOCAL.md)
- Upgrade roadmap: [UPGRADES.md](../UPGRADES.md)
- Config por projeto: [PROJECT_CONFIG_EXAMPLES.md](./PROJECT_CONFIG_EXAMPLES.md)
- Calibração: [CALIBRACAO_LLM.md](./CALIBRACAO_LLM.md)
