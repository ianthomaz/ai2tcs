# bikeanjoall_2026

Manifesto do Bike Anjo no ai2tcs (docs/27). Primeiro projeto instalado e o estudo de caso.

| | |
|---|---|
| Missão | informar quem escreve para o Bike Anjo e levar a pessoa à tela certa (inscrição, cadastro, formulário de saúde), sem deixar no vácuo e sem conversar |
| Canais | `whatsapp` (Zap do Bike Anjo); depois `email` e `ticket` |
| Conhecimento (RAG) | pasta `LLM/rag/` do repositório do Bike Anjo (`BIKEANJOALL_2026_SOURCES`) |
| Contratos de porta | `llm_api/contracts/bikeanjo/` (espelho do repositório do Bike Anjo) |
| Regras da casa | herda todas de `_shared/regras-da-casa.md` |

## Regras da casa que este projeto não segue

Nenhuma.

## O que fica aqui

| Pasta | Conteúdo | Lida por |
|---|---|---|
| `diretrizes/postura-ask.md` | forma e postura da resposta do `/ask` (fim do system prompt) | `scripts/seed_bikeanjoall.py` → `config_json.system_instruction` |
| `diretrizes/postura-router.md` | tom do roteador | seed → `config_json.router.extra_system_block` |
| `casos/eval_questions.json` | 85 casos reais do shadow, anonimizados e com `bucket` | portão de avaliação |

Mudou um arquivo de `diretrizes/`: rodar o seed de novo (o texto vai para o banco).
