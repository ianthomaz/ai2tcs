# 19 — Revisão de otimização da LLM (out/2026)

**Natureza:** leitura do código na `main` (`1c18b80`) e do cliente Bike Anjo
(`bikeanjo2026all@ee200925`, já com a leitura de resposta do Zap), com achados e um plano em ondas. Nada aqui muda regra do
jogo de uma vez: cada item entra ao lado do que existe, medido antes e depois. O que
pede decisão do dono está marcado **decidir**.

Documentos irmãos: [11](./11-improvements-roadmap.md) (roadmap antigo) ·
[13](./13-optimization-execution-plan.md) (plano incremental) ·
[18](./18-bikeanjo-ops-ports.md) (portas do Bike Anjo).

---

## 1. Como uma mensagem do Zap anda hoje

```text
WhatsApp → zapzap
  message-intent.js (PARE: oi/obrigado/emoji/robô alheio → silêncio, sem LLM)
  POST /router  (modelo fast, RAG: mensagem + cidade/interesse/jornada)      ← síncrono
    answer_now → texto do roteador
    escalate   → POST /ask (fila, modelo smart, RAG: só a pergunta)         ← job + polling
                   sanitize → guard (forbidden_terms) → no_answer se vazio
  shadow: grava hipótese + contexto + suggested_action; nada é enviado

Resposta a mensagem que pede retorno (confirmação de presença, avaliação, pagamento):
  zapzap reply-reader.js: regra primeiro; na dúvida
  POST /extract step reply_intent (modelo fast, sem RAG, lista de códigos na pergunta)
  zapzap confere o código contra a lista do contexto; shadow, nunca responde
```

Por mensagem que passa do PARE: **2 embeddings, 2 buscas no Chroma, 2 chamadas de
modelo** (fast + smart). As duas consultas de RAG são diferentes (o roteador acrescenta
contexto à mensagem), então o cache de embedding não as junta.

### Tamanho do prompt do `/ask` do Bike Anjo (medido)

| Parte | Caracteres | Origem |
|---|---|---|
| `system_prompt` do cliente | 4.882 | `zapzap/flows.js` `DEFAULT_SYSTEM_PROMPT` |
| system do serviço (abertura, calibração, regras, perfil, `system_instruction`) | 1.950 | `app/rag/prompt.py` + seed |
| user (5 trechos × 512 + pergunta) | 2.859 | `build_messages` |
| histórico | até 10 × 2.000 | `__llm_history` (cliente) |
| **Total sem histórico** | **≈ 9.700 (~2,8–3 mil tokens)** | |

---

## 2. Achados

Classificação: **M** = medir antes de mexer · **B** = ganho barato, sem mudar contrato ·
**Q** = qualidade das decisões · **V** = versatilidade · **H** = higiene.

| # | Tipo | Achado | Onde |
|---|---|---|---|
| A1 | H | **[resolvido out/2026: `triage-v2` no git, ver 18 § 9]** **O que roda no mini62 não estava no git.** O Bike Anjo registra `triage-v2` publicado no ai2tcs do mini62 em 2/out (AC8, eval PRONTO). Nenhum commit do ai2tcs no GitHub tem `triage-v2`: `app/bikeanjo/feedback_triage.py` diz `triage-v1` e `contracts/bikeanjo/prompts/` não tem `feedback-triage-v2.md`. Um deploy a partir da `main` volta a triagem para v1. | `feedback_triage.py:23` |
| A2 | M | **`num_ctx` nunca é definido.** `get_llm_config` não passa `num_ctx`; o Ollama usa o padrão da versão instalada (2048 ou 4096). O prompt do Bike Anjo tem ~3 mil tokens antes do histórico. Se passar do limite, o Ollama descarta parte do prompt para caber, sem erro, mantendo só os primeiros tokens; as regras do system prompt, que vêm logo depois, são o trecho mais exposto. Pode explicar parte do «ignora a regra» do shadow. | `registry.py:153`, `ollama_provider.py` |
| A3 | M | **As métricas do Ollama são descartadas.** A resposta traz `prompt_eval_count`, `eval_count`, `total_duration`, `load_duration`; `OllamaProvider.chat` devolve só o texto. Sem isso não se sabe tokens por job, tempo de carga do modelo nem se A2 acontece. | `app/llm/ollama_provider.py` |
| A4 | B | **`/router` e `/extract` chamam o Ollama direto.** Sem `asyncio.wait_for` (um Ollama travado prende a requisição), ignoram `config_json.llm_provider` do projeto e não passam pelo provider. O `/ask` já tem `_chat_or_timeout`. O `/extract` atende também a leitura de resposta do Bike Anjo (`reply_intent`). **`/extract`: teto de tempo aplicado (out/2026, `EXTRACT_TIMEOUT_S`); falta o provider.** | `message_router.py`, `extract.py` (blocos `ollama.chat`) |
| A5 | B | **Um cliente Chroma novo por consulta.** `_retrieve_from_path` cria `chromadb.PersistentClient` a cada busca (2× por mensagem, 3× com deep search). Cache de cliente/coleção por caminho, invalidado no ingest, tira esse custo fixo. | `app/rag/retrieve.py:36` |
| A6 | B | **A ordem do system prompt desperdiça o cache de prefixo do Ollama.** O Ollama reaproveita o processamento do início do prompt quando ele se repete. Hoje o perfil da pessoa (muda a cada contato) vem **antes** do bloco fixo do projeto (`system_instruction`). Fixo primeiro, variável depois, é o mesmo texto em outra ordem — mas muda o que o modelo lê por último, então entra com eval antes/depois. | `prompt.py` `build_system_prompt` |
| A7 | Q | **A confiança do `/ask` não é sinal.** `confidence = "high" if chunks else "low"`. A do `/router` é autodeclarada pelo modelo e já foi vista alta em respostas 👎 (backlog Bike Anjo R1). Há sinais determinísticos baratos e honestos: distância do melhor trecho, quantos trechos passaram do limiar, se o guard ou o sanitize mexeu, tamanho da resposta. | `worker.py:518`, `message_router.py` |
| A8 | Q | **Padrões de amostragem pensados para texto longo.** O bot do Bike Anjo herda `temperature 0.5` e `repeat_penalty 1.3`. Penalidade de repetição alta em resposta curta em português castiga `de`, `a`, URLs repetidas. É configuração por projeto (`llm_options`), sem código: A/B com o eval. | `registry.py:166` |
| A9 | H | **Duas fontes do comportamento do bot.** `flows.js` manda 4,9 mil caracteres de regra a cada `/ask`; o seed do ai2tcs tem outras 1,1 mil (`BIKEANJO_SYSTEM_INSTRUCTION`). Parte se repete, e o texto do cliente está em pt-PT («acções», «és», «manténs») enquanto proíbe «telemóvel». Regra repetida em dois lugares diverge com o tempo. | `zapzap/flows.js:716`, `scripts/seed_bikeanjoall.py` |
| A10 | Q | **Conflito de tom no roteador.** `ROUTER_SYSTEM` pede resposta «friendly»; o bloco do Bike Anjo, anexado depois, pede «sem entusiasmo». O modelo pequeno (fast) resolve como quiser. | `message_router.py` `ROUTER_SYSTEM` |
| A11 | Q | **Três avaliações soltas.** `scripts/eval_rag.py` (perguntas-ouro, já compara config antes/depois), `scripts/eval_bikeanjo_ops.py` (portas de texto) e o adaptador shadow→eval no Bike Anjo. Não há um comando único que diga «esta mudança de prompt/config piorou alguma coisa». | `scripts/` |
| A12 | V | **O motor genérico já existe, com nome de projeto.** `app/bikeanjo/common.py` (portão por projeto, envelope, prompt lido de arquivo, `chat_json` com reparo, allowlist) é 80% de um executor de tarefas de texto. O passo `reply_intent` em `/extract` é mais uma classificação com lista fechada, só que em texto livre (sem `format: "json"`); o serviço confere o código contra a lista que vem na pergunta (out/2026) e o zapzap confere de novo. Cada tarefa nova repete o molde em vez de ser configuração. | `app/bikeanjo/`, `app/api/extract.py` |

Pendências de segurança e operação já listadas e não repetidas aqui: [18 § 9](./18-bikeanjo-ops-ports.md)
(chave de projeto lê `/status` e `/result` de qualquer job; re-ingest de `webplacecc`).

---

## 3. Plano em ondas

Cada onda fecha com o eval da onda anterior rodando igual ou melhor. Nenhuma muda
contrato com cliente.

### Onda 0 — medir e alinhar (antes de qualquer otimização)

1. **A1:** trazer para o git o que roda no mini62 (`triage-v2` e o que mais estiver só lá).
   Conferência: `git status` / `git diff` no checkout do mini62. **Decidir:** commitar
   de lá, ou reescrever aqui a partir do contrato do Bike Anjo.
2. **A3:** o provider devolve texto **e** métricas (`prompt_eval_count`, `eval_count`,
   durações); o worker grava no `Job` (em `user_context_json.__metrics` ou coluna nova) e o
   `/metrics` agrega por projeto. Aditivo: quem lê o texto não muda.
3. **A2:** com A3 no ar, uma semana de leitura: se `prompt_eval_count` encosta no
   `num_ctx` efetivo, há corte. Correção é config (`llm_options.num_ctx` por projeto, ex.
   8192) — com custo de memória a medir no mini62.

### Onda 1 — ganho barato, mesmo comportamento

4. **A4:** `/router` e `/extract` passam por `get_provider(project)` + `_chat_or_timeout`
   (o `/router` com `format: "json"`, já suportado pelo provider). Mesmo prompt, mesma saída.
5. **A5:** cache de `PersistentClient`/coleção por caminho, limpo pelo ingest daquele projeto.
6. **A6:** system prompt na ordem fixo → variável, atrás de flag por projeto
   (`config_json.prompt_order: "static_first"`), ligado só depois do eval igual ou melhor.
7. **A8:** A/B de `llm_options` do `bikeanjoall_2026` (`temperature 0.3`,
   `repeat_penalty 1.1`) com `scripts/eval_rag.py --project bikeanjoall_2026` antes e depois.
   Só configuração.

### Onda 2 — decisões melhores (o que o shadow precisa)

8. **A7:** `/ask` e `/router` devolvem, **ao lado** da confiança atual, um bloco
   `signals` determinístico: `best_distance`, `chunks_kept`, `guard_hit`,
   `sanitize_hit`, `answer_chars`. O shadow grava; a tabela confiança × nota 👍/👎 do
   Bike Anjo passa a ter uma coluna que não é opinião do modelo. Corte de envio
   automático (quando um dia existir) nasce dessa tabela, não da autodeclaração.
9. **A11:** um comando `scripts/eval_gate.py --project …` que roda os conjuntos do
   projeto (ouro + portas + shadow exportado), grava com o diff de config (o
   `eval_rag.py` já faz) e sai com código ≠ 0 quando algum critério cai. Vira o passo
   obrigatório antes de trocar prompt, modelo ou `llm_options`.
10. **A10 + A9:** o texto de comportamento do bot mora num lugar só — a
    `system_instruction` do projeto no ai2tcs (versionada no contrato do Bike Anjo) — e o
    `flows.js` manda só o que é da conversa. Migração aditiva: o serviço ganha o texto
    completo; o cliente deixa de mandar o seu depois do eval igual. **Decidir:** se a
    fonte única fica no ai2tcs (config do projeto) ou no repositório do Bike Anjo (copiado
    como os contratos).

### Onda 3 — versatilidade (porta genérica, sem quebrar as atuais)

11. **A12:** um executor `POST /task/{task_id}`: a tarefa é **arquivo** (prompt,
    allowlist, esquema de entrada/saída, se usa RAG, `prompt_version`) num diretório de
    contratos por projeto; o executor é o `common.py` de hoje sem o nome Bike Anjo. A chave
    do projeto decide quais tarefas ela enxerga.
    - `/feedbackTriage`, `/healthNormalize`, `/replySuggest` e o passo `reply_intent`
      viram tarefas; as rotas atuais continuam como apelido da tarefa (mesmo contrato).
    - A triagem de e-mail e de feedback multi-projeto ([18 § 8](./18-bikeanjo-ops-ports.md))
      nasce como tarefa nova, não como rota nova.
    - Projeto novo que quiser classificar texto escreve arquivos, não código.

---

## 4. O que não muda

- Contratos HTTP atuais (`/ask`, `/router`, `/extract`, NF, boleto, portas do Bike Anjo).
- JSON no fio e na saída do modelo ([18 § 6](./18-bikeanjo-ops-ports.md)).
- Shadow sem envio: toda mudança de decisão passa primeiro pelo shadow e pelo julgamento
  humano.
- Modelos locais (Ollama) como padrão; provider externo continua opcional por projeto.

---

## 5. Decisões em aberto

| # | Pergunta | Saídas | Recomendação |
|---|---|---|---|
| D1 | Como o `triage-v2` do mini62 entra no git (A1) | a) commitar do mini62 · b) reescrever a partir do contrato do Bike Anjo | a — é o código que passou no eval |
| D2 | Fonte única do comportamento do bot (A9/A10) | a) `system_instruction` no ai2tcs · b) arquivo no repositório do Bike Anjo, copiado como os contratos | b — o Bike Anjo já versiona o que o bot sabe; o ai2tcs lê |
| D3 | Ordem da Onda 3 | a) depois das ondas 0–2 · b) já, em paralelo | a — o executor genérico herda as métricas e o gate de eval |

---

**Anterior:** [18-bikeanjo-ops-ports.md](./18-bikeanjo-ops-ports.md)
