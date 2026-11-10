# Prioridades de Atualização para Bike Anjo — ai2tcs (mini62)

**Arquivo:** `prioridades_paraBikeAnjo.md` (raiz do repositório `ai2tcs`)  
**Data:** 10 de novembro de 2026  
**Origem:** Bike Anjo Sistema 2026 (`BikeAnjo_Sistema2026`)  
**Destino:** Repositório `ai2tcs` (`~/Documents/projects/ai2tcs` / `llm_api/`)  
**Status:** Proposta de evolução técnica e alinhamento de contratos HTTP.  
**Ordem de prioridade:** S1 → S3 → S2 → S4  
**Avaliação contra o código e plano:** [docs/21](docs/21-review-nov2026.md) (S2 já está quase coberto pelo `health-v2`).

---

## 1. Contexto Geral

O ecossistema Bike Anjo consome serviços de LLM através do `ai2tcs` (`https://llm.webplace.cc`), cobrindo tanto operações automáticas em segundo plano (`feedbackTriage`, `healthNormalize`, extração de documentos/NFs) quanto operações de auditoria/shadow (`/ask`, `/router`, `/replySuggest`).

Após análise operacional em produção e auditoria de código local, identificamos oportunidades prioritárias de melhoria para viabilizar aprendizado real no Shadow do WhatsApp, mitigar ruídos em saúde e enriquecer a inteligência de feedback com histórico longitudinal.

---

## 2. Solicitações por Porta / Módulo

### S1. Porta `/ask` (RAG / Bot WhatsApp) — Score de Confiança da Resposta
- **Situação Atual:**  
  O `POST /router` devolve `confidence` e `confidence_value` (indicando certeza sobre o roteamento da mensagem), porém o `POST /ask` não devolve score de confiança do texto gerado, apenas telemetria de RAG (`signals`: distância do melhor trecho, número de trechos, token count). No painel `/adm/shadow-llm`, operadores e avaliadores muitas vezes veem uma resposta inadequada associada a uma confiança alta porque o número exibido vinha exclusivamente da decisão do roteador.
- **Solicitação para o ai2tcs:**
  1. No `POST /ask`, incluir no retorno do job final:
     ```json
     {
       "answer": "...",
       "signals": { ... },
       "generation_confidence": 0.82,
       "rag_groundedness_score": 0.91
     }
     ```
  2. Avaliar consistência factual entre os trechos recuperados e a resposta gerada (ex.: score simples de sobreposição semântica ou probabilidade média de tokens-chave) para que o shadow saiba quando a resposta é puramente inferida/alucinada.

---

### S2. Porta `/healthNormalize` — Suporte a v2 (Limitações Físicas e Alergias)
- **Situação Atual:**  
  O contrato v1 (`health-normalize-v1.json`) recebe e higieniza estritamente `medical_conditions` (texto livre de comorbidades). Os campos `physical_limitations` e `allergies` não são inspecionados pelo LLM e dependem 100% de regex/sets mecânicos locais. Quando uma pessoa preenche declarações afirmativas como «bem» ou «saudável» em limitações físicas, isso não era categorizado pelo modelo.
- **Solicitação para o ai2tcs:**
  1. Suportar payload expandido opcional no body:
     ```json
     {
       "conditions_free_text": "...",
       "physical_limitations_free_text": "bem",
       "allergies_free_text": "nao"
     }
     ```
  2. No retorno, mapear os resíduos limpos para cada campo ou devolver `is_clean_nothing: true` quando o texto apenas reafirmar ausência de restrições.
  3. Manter a premissa fundamental: o LLM **nunca diagnostica nem julga gravidade** clínica; apenas normaliza termos e expurga ruídos semânticos.

---

### S3. Shadow Learning Loop — Automação da Retroalimentação de Julgamentos
- **Situação Atual:**  
  A tabela `zapzap_shadow_ratings` em produção acumula avaliações de operadores (`👍 / 👎`, motivos como `prometeu_fora_da_regra`, `link_inventado`, etc.). Porém, a ingestão desse feedback no corpus vetorial (`bikeanjoall_2026`) ainda depende de intervenção manual através do script `shadow-learn-to-ai2tcs.sh`.
- **Solicitação para o ai2tcs:**
  1. Criar endpoint ou rotina programada `POST /corpus/shadow-feedback` (ou via batch) para absorver automaticamente respostas reprovadas como **exemplos negativos / forbidden patterns** no prompt do projeto.
  2. Quando uma resposta for rejeitada por «prometeu presença» ou «inventou link», adicionar o padrão na lista de exclusão/trava sintática em tempo de geração.

---

### S4. Porta `/feedbackTriage` — Aproveitamento de Dados Longitudinais do Sujeito
- **Situação Atual:**  
  O Bike Anjo já envia `historico.*` (tentativas antes, dificuldades, marcos de evolução) quando disponível. No entanto, o prompt `feedback-triage-v2.md` no `ai2tcs` ainda dá peso quase exclusivo aos campos imediatos do feedback pontual (`impressao_curta`, `recado_livre`).
- **Solicitação para o ai2tcs:**
  1. Ajustar o prompt de triagem para correlacionar a evolução histórica: uma pessoa com histórico de «medo intenso» ou «trauma» que conclui a oficina EBA com avaliação 5 deve receber tag `aprendizado` e nota de solidez alta (`answer_solidity: 5`), pois reflete impacto transformador comprovado por dados anteriores.

---

## 3. Resumo da Ordem de Prioridades

| ID | Porta | Impacto | Esforço Estimado |
|---|---|---|---|
| **S1** | `/ask` | Alto (calibração do Shadow WhatsApp) | Médio |
| **S3** | Shadow Learning | Alto (fechamento do ciclo de aprendizado) | Médio |
| **S2** | `/healthNormalize` v2 | Médio (redução de resíduos em saúde) | Pequeno |
| **S4** | `/feedbackTriage` | Médio (inteligência de impacto social) | Pequeno |
