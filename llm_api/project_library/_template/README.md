# {project_id}

Manifesto do projeto no ai2tcs (docs/27). Copiado por `scripts/create_project.py`.

| | |
|---|---|
| Missão | o que a LLM faz por este projeto, numa frase |
| Canais | `whatsapp` · `email` · `ticket` · `form` · `chat` |
| Conhecimento (RAG) | `rag/` desta pasta, ou a pasta `LLM/rag/` do repositório do projeto |
| Regras da casa | herda todas de `_shared/regras-da-casa.md`; as que recusa ficam listadas abaixo, com o motivo |

## Regras da casa que este projeto não segue

Nenhuma.

## O que fica aqui

| Pasta | Conteúdo | Lida por |
|---|---|---|
| `rag/` | conhecimento do projeto (só quando ele não tem pasta `LLM/rag/` própria) | ingest |
| `diretrizes/` | tom, limites, instrução de comportamento | prompt do `/ask` (`behavior_instruction_path`) e professor |
| `casos/eval_questions.json` | casos de ouro, anonimizados | portão de avaliação |
