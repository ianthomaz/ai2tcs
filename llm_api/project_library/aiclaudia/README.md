# aiclaudia

Manifesto no ai2tcs (docs/27). Laboratório de conversa: é aqui que se vê se a LLM local
conversa bem, antes de soltar conversa num projeto com demanda real.

| | |
|---|---|
| Missão | chatbot criativo do projeto aiClaudia; desligado em nov/2026, volta refeito (com animação) |
| Canais | `chat` (interface própria) |
| Conhecimento (RAG) | pasta `rag/` do repositório 033_aiClaudia (`AICLAUDIA_SOURCES`) |
| Custo | só LLM local; conversa à vontade, com limite por sessão |
| Regras da casa | herda as de qualquer canal (5 a 10) |

## Regras da casa que este projeto não segue

- 1 a 4 (conversa por mensagem): conversar é a função dela (dono, 13/nov/2026).

## O que fica aqui

| Pasta | Conteúdo | Lida por |
|---|---|---|
| `casos/eval_questions.json` | casos de regressão, inclusive os de assunto fora da base (`forbidden_keywords`) | portão de avaliação |
