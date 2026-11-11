# Guia de Autonomia de LLM Local, Upgrades de Mercado e Trilha de Aprendizado

**Data:** 2026-11-10  
**Contexto de Máquina:** Mac mini M4, 32 GB RAM Unificada (Apple Silicon), ~34 GB livres em disco.  
**Projetos Centrais:** `bikeanjoall_2026` (WhatsApp/Check-in/MCP), `chinese_learning` (Tutor EDU/SRS), `033_aiClaudia` (Ressurreição com limites) e ecossistema `0MM_ITCS`.

---

## 1. Diagnóstico do Hardware: Aproveitando 70% dos 32 GB de RAM

Seu Mac mini M4 tem **34.359.738.368 bytes (32 GB)** de memória unificada (CPU e GPU compartilham o mesmo pool com altíssima largura de banda).
- **Alocação Ideal (~70% = ~22 a 24 GB para LLMs/VRAM):**
  - Sistema Operacional macOS + Docker + PostgreSQL: **~6 a 8 GB**
  - Espaço reservado e ativo para Modelos no Ollama (Metal GPU): **~22 a 24 GB**
- **Ponto de Atenção Atual (Disco):**
  - O volume principal está com **92% de ocupação (34 GB livres de 460 GB)**.
  - Modelos de 14B a 32B quantizados pesam entre 9 GB e 20 GB. Portanto, antes de baixar modelos novos, é prudente limpar caches antigos do Docker (`docker system prune`) ou modelos não usados no Ollama (`ollama rm <modelo>`).

---

## 2. Panorama Atualizado de Modelos Locais (O que o Mercado Oferece Hoje)

Para rodar nos seus ~22 GB disponíveis com velocidade de produção, estas são as melhores opções da atualidade:

| Família / Modelo | Tamanho (Q4_K_M) | Consumo de RAM | Pontos Fortes no seu Contexto | Onde encaixa no `ai2tcs` |
|---|---|---|---|---|
| **Qwen 2.5 14B / 32B** | 14B: ~9 GB<br>32B: ~20 GB | 14B: ~11 GB<br>32B: ~22 GB | Melhor modelo open-source do mundo para **Structured Outputs (JSON)**, Function Calling / Tool Use e **Mandarim/Chinês** nativo sem sotaque. O 32B cabe à risca nos 70% de RAM. | **Substituto ideal para `smart` e `reasoner`**. Revoluciona o `chinese_learning` e o Bike Anjo. |
| **Qwen 2.5 Coder 14B / 32B** | 14B: ~9 GB<br>32B: ~20 GB | ~11 a 22 GB | Excelente em lógica determinística, extração de dados fiscais (NF/Boleto) e interpretação de schemas JSON. | `smart` voltado para tarefas de código e MCP. |
| **Gemma 2 / Gemma 3 12B / 27B** | 12B: ~8 GB<br>27B: ~17 GB | 12B: ~10 GB<br>27B: ~19 GB | Português brasileiro impecável, tom muito natural e alta fidelidade ao contexto fornecido no RAG (baixo índice de alucinação). | `smart` canônico para o Bike Anjo e conversação em PT-BR. |
| **Llama 3.1 / 3.3 8B / 70B** | 8B: ~5 GB | ~6 GB | O 8B é imbatível em velocidade para roteamento instantâneo. (O 70B exige 40 GB+, não cabe nos 32 GB). | **Insubstituível no alias `fast`** (para o `/router` em menos de 1 segundo). |
| **DeepSeek R1 Distill 14B / 32B** | 14B: ~9 GB<br>32B: ~20 GB | ~11 a 22 GB | Raciocínio explícito (Chain of Thought). Excelente para triagem complexa de denúncias ou regras de negócio intrincadas. | Alias `reasoner` quando a tarefa exige pensar antes de responder. |

### Configuração de Ouro Sugerida para os seus 32 GB:
Manter **2 modelos residentes na memória** simultaneamente (`OLLAMA_KEEP_ALIVE=-1`):
1. **`fast` (Llama 3.1 8B Q4 ~ 5 GB):** Fica 100% quente na RAM para o `/router` responder em 400ms no WhatsApp.
2. **`smart` (Qwen 2.5 14B ou 32B Q4 ~ 11 a 20 GB):** Fica quente na RAM atendendo RAG, Bike Anjo, Chinês e MCP.
Total residente: ~16 a 24 GB. Zero tempo de espera (`load_ms = 0`) na primeira mensagem do dia!

---

## 3. O que falta para a LLM ter Mais Autonomia (Projeto a Projeto)

Hoje você sente o sistema "muito assistido" porque ele foi desenhado para **prevenção máxima de dano** (o que foi corretíssimo na fase 1). Para dar o próximo passo com segurança:

### 3.1 Bike Anjo: Da Consulta ao "Check-in Inteligente" (Rumo a MCP / Tools)
- **O que impede a autonomia hoje:** A LLM só responde texto informativo; ela não tem "mãos" para agir no banco de dados.
- **Como dar autonomia com segurança (O Padrão Proposta $\rightarrow$ Validação):**
  - **Tool Use / Function Calling:** O modelo recebe ferramentas declarativas:
    - `consultar_eventos(cidade, data)`
    - `propor_checkin(participante_id, evento_id)`
    - `consultar_vagas_oficina(local_id)`
  - **A virada de chave:** A LLM **propõe** o JSON da ação. O backend valida regras de negócio (capacidade da oficina, idade mínima, autenticidade) e executa no Postgres.
  - **Acesso via Antigravity:** Quando você conectar o `ai2tcs` via MCP no Antigravity, você mesmo pode pedir no chat: *"Agente, verifique as inscrições da oficina de sábado no Bike Anjo e sugira as mensagens de confirmação para os voluntários pendentes"*.

### 3.2 Chinese Learning: Autonomia Pedagógica Ativa
- **O que impede a autonomia hoje:** O modelo responde perguntas de forma reativa, sem saber o que o aluno errou ontem.
- **O que fazer:** Injetar no prompt do `/edu/chat` o estado de retenção do aluno (tabela `edu_progress`).
- **Comportamento Autônomo:** Se o aluno fala *"Bom dia, como vai?"*, o tutor responde e já emenda uma pergunta usando sutilmente as 2 palavras do HSK1 em que o aluno tem menor taxa de acerto (`seen_count > 0, mastered = false`). O tutor guia a aula em vez de só esperar perguntas.

### 3.3 Ressurreição da Claudia (`033_aiClaudia`): Autonomia Controlada
- **Por que ela foi desligada:** Personas criativas e abertas tendem a desviar de assunto, cansar em turnos longos ou vazar dados de outros projetos.
- **Como religar com segurança:**
  1. **Teto de Turnos:** Guard que encerra a sessão ou resume o histórico após 6 trocas.
  2. **Isolamento de Base:** `rag_mode: disabled`, `forbidden_terms` ativos e sem acesso às tabelas globais.
  3. **Modelo Leve e Barato:** Rodar Claudia exclusivamente no alias `fast` ou `compact` com temperatura 0.7 e prompt fechado de persona.

---

## 4. Trilha de Aprendizado Curada: O que Estudar e Assistir no YouTube

Para não perder tempo com vídeos superficiais de "hype", aqui estão os conceitos e canais que realmente ensinam engenharia de ponta em agentes e LLMs locais:

### 4.1 Conceitos-Chave para Pesquisar e Dominar
1. **Model Context Protocol (MCP):**
   - Entenda a especificação oficial da Anthropic que virou o padrão da indústria para conectar agentes a bancos, APIs e ferramentas locais.
   - *Termos de busca:* `"Model Context Protocol architecture"`, `"Building MCP servers with Python"`.
2. **Function Calling & Structured Outputs em Ollama:**
   - Como forçar modelos como Qwen 2.5 a devolver schemas JSON perfeitos e decidir sozinhos quando chamar uma ferramenta.
   - *Termos de busca:* `"Ollama tool calling Python"`, `"Qwen 2.5 function calling local"`.
3. **Agentic Workflows (Design Patterns de Andrew Ng):**
   - Os 4 padrões de agentes: Reflexão (Self-Reflection), Uso de Ferramentas (Tool Use), Planejamento (Planning) e Multi-Agent Collaboration.
   - *Termos de busca:* `"Andrew Ng Agentic Design Patterns"`.
4. **Apple Silicon Unified Memory & LLM Inference (Metal):**
   - Como o macOS gerencia memória compartilhada entre CPU e GPU e por que o Mac mini M4 de 32 GB compete com placas dedicadas.
   - *Termos de busca:* `"Apple Silicon unified memory LLM benchmark"`, `"Ollama GPU memory allocation macOS"`.

### 4.2 Canais de Alta Qualidade no YouTube (Sem Clickbait)
- **Matt Wolfe / AI Explained:**
  - Análises profundas de atualizações reais de modelos e mercado, comparando benchmarks e autonomia de agentes.
- **Prompt Engineering (Canal do YouTube):**
  - Tutoriais passo a passo rodando Ollama local, conectando MCP servers, LangGraph e testando modelos quantizados.
- **Harrison Chase (LangChain / LangGraph) & Anthropic Developers:**
  - Palestras sobre arquitetura de agentes que não alucinam, controle de estado e integração de ferramentas seguras.
- **Underfitted (ou Greg Kamradt):**
  - Mestre em visualização de RAG, chunking strategies e orquestração de memória de longo prazo.

---

## 5. Mapa de Evolução (Backlog Macro)

Este backlog não é para execução imediata, mas para nortear o futuro:

### Onda 1: Otimização de Hardware e Modelos (Ganho Imediato)
- [ ] Limpeza de disco no mini62 (liberar para ter ~60 GB livres).
- [ ] Testar `qwen2.5:14b` ou `qwen2.5:32b` no alias `smart` para avaliar ganho de qualidade no Bike Anjo e no Chinês.
- [ ] Ajustar `OLLAMA_KEEP_ALIVE=-1` para manter os 2 modelos principais carregados na RAM sem latência de boot.

### Onda 2: Acesso Remoto MCP no Antigravity
- [ ] Criar o script bridge MCP unificado que consome `ai2tcs` (`:28471`), `0mmS_Tasks` (`:28501`) e `0MM_ITCS` (`:28500`).
- [ ] Permitir que do chat do Antigravity você possa rodar testes ao vivo, auditar jobs e inspecionar a saúde do cluster.

### Onda 3: Transações Seguras no Bike Anjo via Chat (Tools)
- [ ] Implementar rotas de simulação de check-in / presença onde a LLM apenas propõe o payload e o sistema valida.
- [ ] Criar catálogo de intents aprovadas para o bot agir com supervisão em 1 toque do usuário.

### Onda 4: SRS Ativo no Chinese Learning
- [ ] Integrar `edu_progress` no prompt do tutor para repetição espaçada autônoma.
- [ ] Suporte a áudio e pronúncia via Whisper local.
