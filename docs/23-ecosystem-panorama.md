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
| Pergunta curta de continuação («e em Curitiba?») busca sem o contexto da conversa | **disponível**, desligada: `policies.retrieval_query_with_history` soma a pergunta anterior da pessoa quando a atual tem até 3 palavras de conteúdo (só a busca muda); o `/router` já soma contexto |
| Corte de trechos repetidos do mesmo documento (`_rerank_for_diversity` só reordena) | **aberto**, só com o portão de avaliação |

Ordem completa da busca: [12 § Busca](./12-llm-fleet-rag-operations.md#busca-como-um-trecho-chega-ao-prompt).

## 4. Conversa com mais liberdade

Meta: o robô responder sozinho, em conversa que a pessoa começou por um aplicativo de
mensagem, sem prometer o que não pode. O caminho é medir antes de soltar, com a mesma
porta para a medida e para o envio.

Direção do dono (10/nov/2026): primeiro um robô que **informa** (pelo menos não deixa a
pessoa no vácuo), pouco semântico. O passo grande depois é um robô que **age no sistema**,
quase um MCP do sistema: «quero me inscrever na oficina X» → acha a oficina e inscreve. Isso
vai além de responder pela base e, quando vier, abre espaço maior de uma vez. A confiança
para cada passo vem da conta «o robô teria respondido sozinho?» (etapa 3), não de um número
combinado antes.

| Etapa | O que é | Situação |
|---|---|---|
| 1. Sinais honestos | confiança da resposta calculada só dos fatos (distância, apoio dos trechos, trava, link fora da base) | **feito** (`signals-v1`) |
| 2. Critério de envio | o cliente decide, por uma porta, se o texto sairia (no Bike Anjo: `zapzap/lib/llm-send-gate.js`: confiança ≥ 0,70, sem trava, sem link fora da base, pergunta sobre a associação) | **feito**; o shadow grava em toda hipótese se ela passaria |
| 3. Medida | cartão «O robô teria respondido sozinho?» no `/adm/shadow-llm`: teria respondido e estava boa / ruim, teria ficado em silêncio e estava boa / ruim, e os motivos de silêncio; por semana no cartão «Evolução» | **feito**; precisa de julgamentos |
| 4. Ligar o envio | `llm_send` ligado; sai só o que passa no critério, o resto fica no shadow | decisão do dono, quando a conta der confiança |
| 5. Aprender com o que sai | julgamentos → termo proibido aprovado, exemplos aprovados no prompt (`policies.rated_examples`) | **feito** no serviço; exemplos desligados até o portão |
| 6. Roteador guiado pelos sinais | `answer_now` do modelo pequeno rebaixado para `escalate` quando a busca não trouxe base | aberto |
| 7. Outros aplicativos | qualquer cliente de conversa usa a mesma porta de critério e de julgamento | aberto; o ai2tcs já é genérico |
| 8. Robô que age no sistema | a LLM escolhe uma ferramenta do sistema (buscar oficina, inscrever, consultar a própria situação) e o sistema executa e confere; o texto vem da ferramenta, não da base. Semente: a intenção do `/ask` (`intent.action`, já com `event_interest_lookup`) | direção; depois da etapa 4 |

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

## 8. Roteiro único do ai2tcs

Lista única do que segue aberto no serviço, conferida contra o código em 10/nov/2026. Os
planos antigos ([00](../llm_api/00_PLANEJAMENTO_LLM_LOCAL.md), [UPGRADES](../llm_api/UPGRADES.md),
[11](./11-improvements-roadmap.md), [13](./13-optimization-execution-plan.md),
[16](./16-code-review-findings.md), [17](./17-integration-backlog.md), [19](./19-optimization-review.md))
apontam para cá; o que eles marcam como feito está no código.

| Frente | Item | De onde | Tamanho |
|---|---|---|---|
| Segurança e operação | Bike Anjo: assistente de pagamento usar `llm_reading` (mensagem «leitura indisponível, nota guardada» e «Tentar novamente» sem duplicar a nota na fila do Drive) | dono, 11/nov | pequeno |
| | limite de chamadas por projeto (hoje nenhum) | 00 | médio |
| | limite de tentativas no login do dashboard (nada no código; pode estar na borda) | 16 § 1.4 | pequeno |
| | migrar os outros projetos para a chave própria e pô-los em `SCOPED_KEY_REQUIRED_PROJECTS` | 17 | operação |
| | logs estruturados (JSON) | 00 | pequeno |
| | troca de provider quando o principal cai | 16 § 1.9 | médio |
| Qualidade da resposta | cortar trechos repetidos do mesmo documento | 16 § 1.3 | pequeno, com o portão |
| | ingest de PDF e DOCX (as bibliotecas já estão instaladas) | 16 § 1.8 | médio |
| | variação do system prompt para respostas menos repetidas | UPGRADES nível 3 | pequeno, com o portão |
| | limite de latência p95 por rota | 13 | pequeno |
| API | `/ask/stream` (resposta em pedaços) | 11 | médio |
| | `/v1/chat/completions` compatível com OpenAI | 11 | médio |
| | roteamento por complexidade (modelo pequeno ou grande pela pergunta) | 11 | médio |
| | `/router` devolve o que a pessoa já disse (`extracted_prefill`) | § 5 | pequeno |
| | roteador guiado pelos sinais; robô que age no sistema | § 4, etapas 6 e 8 | médio a grande |
| Ecossistema | MCP local para ai2tcs, Tasks e 0MM | § 5, 11 | médio |
| | `itcsManifest.yaml`: `port` e `pathRemote` em `spec.envs`; o hub nunca leu o cartão (`lastHarvestAt`) | 17 | pequeno |
| | lista dos projetos ativos para o hub | 17 | pequeno |
| | fila para quando o serviço cai (nasce no cliente) | § 5 | médio |
| | tutor que lembra dos erros e exercício sem LLM (`/edu`) | § 5 | pequeno cada |
| Projetos e aprendizado ([27](./27-projetos-e-aprendizado.md)) | prompt do `/ask` monta regras da casa + postura do projeto (hoje cada postura repete a casa), com o portão em cada projeto | dono, 13/nov | médio |
| | limite por sessão na conversa com a LLM local (laboratórios `aiclaudia` e `chinese_learning`) | dono, 13/nov | pequeno |
| | casos de ruído do WhatsApp (saudação, emoji, resposta automática) num arquivo comum, rodados em todo projeto do canal | dono, 13/nov | pequeno |
| | `webplace` na pasta do projeto: instrução em `diretrizes/`, fora da busca | 27 § 6 | pequeno, com casos novos |
| Decisões do dono | `nf_number` recusar o que não parece número de nota (troca recall por segurança) | 16 § 1.6 | — |

---

**Anterior:** [22-answer-ratings.md](./22-answer-ratings.md)
