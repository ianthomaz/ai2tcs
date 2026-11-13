# Treinamento e inteligência LLM

Pasta canônica do **ai2tcs** para treinar a LLM local com casos reais (shadow do
Bike Anjo e outros projetos), segunda opinião no mini62 e higiene de avaliação.
Não é contrato de porta JSON (isso continua em `llm_api/contracts/bikeanjo/` e no
espelho Bike Anjo `docs/contracts/ai2tcs/`).

## Ler nesta ordem

| Arquivo | Conteúdo |
|---|---|
| [segunda-opiniao-agente.md](./segunda-opiniao-agente.md) | Desenho: professor Cursor/Antigravity, caso AAJA9 (liberar vaga), janela de tempo, só consulta → «já liberada» / «use o botão», fases até ação |
| [fases-e-cotas-fins-de-semana.md](./fases-e-cotas-fins-de-semana.md) | Funil por fins de semana (30 → 20 → 10/dia), papéis (Cursor na prod vs Antigravity no código) e filtro de perguntas bestas |
| [roteiro-10-passos-implementacao.md](./roteiro-10-passos-implementacao.md) | Fronteiras exatas (Bike Anjo vs ai2tcs), tom sem papo furado, proposta de ação e roteiro conciso dos 10 primeiros passos |
| [contrato-segunda-opiniao.md](./contrato-segunda-opiniao.md) | Schemas JSON formais (Payload e Response) e exemplos canônicos (caso AAJA9 com botão usado vs sem botão) |
| [isolamento-e-execucao-mini62.md](./isolamento-e-execucao-mini62.md) | Travas estruturais no mini62, worker do host (`second_opinion_worker.py`), cotas no banco e modelo reativo via campainha |
| [higiene-eval-ask.md](./higiene-eval-ask.md) | Buckets A/B/C/D do `/ask`, o que o 5/85 mistura, ordem de flags, o que não fazer |
| [agentes-seguros-mini62.md](./agentes-seguros-mini62.md) | Como rodar Cursor e Antigravity com recorte duro; o que **não** reutilizar (`zapCursorAgent`); Gemini como fallback depois |
| [cursor-cli-perguntas.md](./cursor-cli-perguntas.md) | Cursor CLI sem tela no mini62: o que a documentação garante, perfil restrito (`CURSOR_CONFIG_DIR`), perguntas para o próprio Cursor e prova |
| [avaliacao-do-plano.md](./avaliacao-do-plano.md) | Leitura do plano contra o código: o que mudar (fila no banco + worker no host, professor não aprova exemplo sozinho) e ordem no ai2tcs |

## Já existe noutros docs do ai2tcs (não duplicar)

| Doc | Papel |
|---|---|
| [22-answer-ratings.md](../22-answer-ratings.md) | `POST /ratings` · propostas · exemplos `great` |
| [12-llm-fleet-rag-operations.md](../12-llm-fleet-rag-operations.md) | Frota, ingest, operações RAG |
| [24-ops-observe.md](../24-ops-observe.md) | Observe genérico (contagens; **não** basta para inscrição de uma pessoa) |
| [18-bikeanjo-ops-ports.md](../18-bikeanjo-ops-ports.md) | Portas ops BA (triagem, saúde, replySuggest) |
| [23-ecosystem-panorama.md](../23-ecosystem-panorama.md) | Panorama ecossistema |
| `llm_api/contracts/bikeanjo/` | Esquemas / hints / `ask-intent.eval.json` (espelho do monorepo BA) |

## Lado Bike Anjo (só ponte)

- Prosa Zap / shadow: `BikeAnjo_Sistema2026/docs/07b_ZAP_FLUXOS_E_LLM.md` § shadow avançado
- Stub: `docs/contracts/ai2tcs/SEGUNDA_OPINIAO_AGENTE.md` → aponta para **esta** pasta
- Corpus / ingest: biblioteca + `tools/scripts/llm-ingest-bikeanjo.sh`

## Estado

Proposta e casos (12/nov/2026). A fila existe no código, desligada: [26-second-opinion.md](../26-second-opinion.md)
é o contrato que vale (genérico por projeto e canal); os esquemas de
`contrato-segunda-opiniao.md` são o desenho do caso do Bike Anjo. Avaliação do plano e o que
mudou: [avaliacao-do-plano.md](./avaliacao-do-plano.md).
A nota solta `RAG_melhorias_tmp.md` na raiz do ai2tcs foi absorvida em
`higiene-eval-ask.md` e removida.
