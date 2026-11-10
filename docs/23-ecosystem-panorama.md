# 23 — Panorama: ai2tcs no ecossistema ITCS e o caminho da LLM

Visão de conjunto do serviço, do que já está feito e da ordem do que vem. Reúne a revisão de
arquitetura de 9/nov/2026 e as prioridades que o Bike Anjo pediu em 10/nov/2026; a
avaliação ponto a ponto, contra o código, está em [21](./21-review-nov2026.md).

Princípio: o ai2tcs serve vários projetos; o Bike Anjo é o primeiro cliente e traz as
demandas, mas toda capacidade nasce genérica ([README § Princípio](../README.md#princípio-serviço-de-vários-projetos)).
Modo de execução: fatiar pequeno, confirmar antes de destruir, conferir antes de declarar
feito, uma frente por vez.

---

## 1. Onde o ai2tcs está no ecossistema

| Pilar | Serviço | Papel |
|---|---|---|
| Governança e catálogo | `0MM_ITCS` | projetos, máquinas, domínios, manifestos, saúde |
| Estado operacional | `0mmS_Tasks` | quadro de tarefas por projeto |
| Cognição | `ai2tcs` (mini62, `llm.webplace.cc`) | LLM local (Ollama), RAG por projeto, tarefas de texto, extração de documento, voz, tutor |

O `0MM_ITCS` monitora o ai2tcs por `GET /health?strict=1` (503 quando Ollama, Postgres ou
disco falham), declarado em `itcsManifest.yaml`.

## 2. O que sustenta o serviço

| Peça | Onde | Doc |
|---|---|---|
| Chave por projeto; chave vê só o seu projeto | `app/auth.py` | [02 § 2.2](./02-api-integration.md) |
| Registro de toda chamada ao modelo (tokens, tempo, pesadas) | `app/llm/metrics.py` | [19 § 6](./19-optimization-review.md) |
| Sinais da resposta e confiança 0–1 só dos sinais | `app/llm/signals.py` | [02 § signals](./02-api-integration.md) |
| Silêncio como resposta válida (`no_answer`), trava por projeto | `app/rag/answer_guard.py` | [08](./08-project-config.md) |
| Tarefas de texto em arquivo, para qualquer projeto | `app/tasks/` | [20](./20-text-tasks.md) |
| Julgamentos de pessoas ensinam o serviço, com aprovação | `app/ratings/` | [22](./22-answer-ratings.md) |
| Portão de avaliação antes de mudar prompt ou configuração | `scripts/eval_gate.py` | [12](./12-llm-fleet-rag-operations.md) |

## 3. RAG: como a base é lida (revisão de 10/nov/2026)

| Ponto | Situação |
|---|---|
| Corte dos trechos: sobreposição não acontecia; parágrafo longo virava trecho de até 5 mil caracteres, dos quais o embedding lê 1.000; dois terços dos pedaços de seção longa perdiam o título | **corrigido no código**; vale no próximo ingest de cada projeto. No Bike Anjo: 808 → 839 trechos, nenhum acima de 512, 12 sem título (eram 259) |
| Dicas de busca por canal (`retrieval_hints`): o contrato do Bike Anjo declarava o que sobe e desce no `/ask`, mas só a sugestão de resposta a chamado aplicava | **corrigido**: configuração do projeto, lida pelo `/ask` e pelo `/router`; o seed do Bike Anjo copia do contrato |
| Reordenação (palavra-chave, dicas, modelo) presa aos mesmos 5 trechos | **corrigido**: pool de 2 × `top_k` |
| Palavra-chave com acento e pontuação («oficina?» não casava com «Oficina») | **corrigido** |
| Instrução de busca do `mxbai-embed-large` na pergunta | **disponível**, desligada: `policies.embedding_query_instruction`, ligar depois do portão |
| Pergunta curta de continuação («e em Curitiba?») busca sem o contexto da conversa | **aberto**: o `/router` já soma contexto à busca; no `/ask`, somar a última pergunta quando a atual for curta, por política do projeto |
| Corte de trechos repetidos do mesmo documento (`_rerank_for_diversity` só reordena) | **aberto**, só com o portão de avaliação |

Ordem completa da busca: [12 § Busca](./12-llm-fleet-rag-operations.md#busca-como-um-trecho-chega-ao-prompt).

## 4. Conversa com mais liberdade

Meta: o robô responder sozinho, em conversa que a pessoa começou por um aplicativo de
mensagem, sem prometer o que não pode. O caminho é medir antes de soltar, com a mesma
porta para a medida e para o envio.

| Etapa | O que é | Situação |
|---|---|---|
| 1. Sinais honestos | confiança da resposta calculada só dos fatos (distância, apoio dos trechos, trava, link fora da base) | **feito** (`signals-v1`) |
| 2. Critério de envio | o cliente decide, por uma porta, se o texto sairia (no Bike Anjo: `zapzap/lib/llm-send-gate.js`: confiança ≥ 0,70, sem trava, sem link fora da base, pergunta sobre a associação) | **feito**; o shadow grava em toda hipótese se ela passaria |
| 3. Medida | por semana: quantas passariam e quantas destas foram julgadas boas (cartão «Evolução» no `/adm/shadow-llm`) | **feito**; precisa de julgamentos |
| 4. Ligar o envio | `llm_send` ligado; sai só o que passa no critério, o resto fica no shadow | espera a medida e a decisão do dono |
| 5. Aprender com o que sai | julgamentos → termo proibido aprovado, exemplos aprovados no prompt (`policies.rated_examples`) | **feito** no serviço; exemplos desligados até o portão |
| 6. Roteador guiado pelos sinais | `answer_now` do modelo pequeno rebaixado para `escalate` quando a busca não trouxe base | aberto |
| 7. Outros aplicativos | qualquer cliente de conversa usa a mesma porta de critério e de julgamento | aberto; o ai2tcs já é genérico |

## 5. Frentes de ecossistema (fora do trabalho do Bike Anjo)

| Frente | Resumo | Situação |
|---|---|---|
| MCP do ecossistema | um MCP local (`stdio`) que fala com ai2tcs, Tasks e 0MM; não toca no container de produção e pode mandar arquivo local para extração | recomendado; aberto, depois de saúde e chaves estáveis |
| Fila para quando o serviço cai | cliente responde o que é determinístico (link canônico), guarda o que precisa de LLM (triagem, chamado, documento) e drena na volta, com um aviso consolidado | aberto; nasce no cliente |
| Tutor que lembra dos erros (`/edu`) | o prompt do tutor recebe as palavras com mais erro do aluno | aberto |
| Exercício sem LLM (`/edu/exercise`) | sorteio no banco quando o Ollama cai | aberto |
| Chat × tela | o chat identifica a intenção e entrega o link certo; a tela coleta o que é denso (formulário com autocompletar). Próximo passo: o `/router` devolver o que a pessoa já disse (`extracted_prefill`) para o link abrir preenchido | princípio adotado; pré-preenchimento aberto |

## 6. Ordem sugerida

1. Deploy desta rodada com o portão de avaliação: snapshot, seed, ingest do Bike Anjo,
   comparação ([CHANGELOG](../CHANGELOG.md)).
2. Duas semanas de julgamentos no `/adm/shadow-llm` para a etapa 3 do § 4.
3. Pergunta de continuação no `/ask` (§ 3) e roteador guiado pelos sinais (§ 4, etapa 6).
4. MCP local (§ 5), depois a fila de queda.

## 7. Pedido do Bike Anjo de 10/nov/2026 (S1–S4)

| Pedido | Situação |
|---|---|
| S1 confiança da resposta do `/ask` | feito: `signals.answer_confidence`, `grounding`, `unsupported_links` |
| S3 aprendizado com os julgamentos | feito: `/ratings` ([22](./22-answer-ratings.md)), com aprovação |
| S2 saúde inteira | feito pelo contrato (alergias, limitações e condições no mesmo texto); resposta por campo só com caso real |
| S4 histórico na triagem | feito: regra 10 do `triage-v2` |

Texto do pedido: `llm_api/contracts/bikeanjo/SOLICITACOES_AI2TCS.md`.

---

**Anterior:** [22-answer-ratings.md](./22-answer-ratings.md)
