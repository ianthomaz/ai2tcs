# 27 — Uma pasta por projeto, e o que um projeto ensina ao outro

O ai2tcs serve vários projetos. Cada projeto instalado tem **uma pasta** neste repositório,
`llm_api/project_library/{project_id}/`, e o que vale para todos mora em `_shared/`. Este
documento diz o que fica em cada lugar e quando um aprendizado passa de um projeto para outro.

## 1. Três camadas

| Camada | Onde | O que é | Exemplo |
|---|---|---|---|
| Serviço | código do ai2tcs (`app/`, `teacher_prompt.md`, `answer_guard`) | o que o serviço garante a qualquer projeto | silêncio como resposta válida (`no_answer`), sinais de confiança, texto da pessoa como dado e não como ordem |
| Regras da casa | `project_library/_shared/regras-da-casa.md` | a lógica de trabalho do dono, comum aos projetos dele | não conversa (2 respostas por assunto), o chat entrega o link e a tela coleta, não promete |
| Projeto | `project_library/{project_id}/` e a pasta `LLM/` do repositório do projeto | o que só vale ali | o corpus, o tom, os casos de ouro, as ações do sistema dele |

Regra de leitura: a camada de baixo pode **recusar** uma regra da casa (no manifesto, com
motivo), nunca a do serviço.

## 2. A pasta do projeto

```text
llm_api/project_library/
├── _template/            ← copiado por scripts/create_project.py
├── _shared/
│   └── regras-da-casa.md
└── {project_id}/
    ├── README.md         ← manifesto: missão, canais, de onde vem o RAG, regras da casa recusadas
    ├── rag/              ← só para projeto sem repositório próprio; com LLM/rag/ no repo dele, não existe
    ├── diretrizes/       ← tom, postura, instrução de comportamento (fora da busca)
    └── casos/
        └── eval_questions.json   ← casos de ouro anonimizados; o portão lê daqui
```

| Peça | Quem lê |
|---|---|
| `casos/eval_questions.json` | `eval_rag.py`, `eval_gate.py`; `import_eval_set.py` grava aqui, separando por `project_id` |
| `diretrizes/` | o seed do projeto (Bike Anjo: `postura-ask.md` e `postura-router.md`) ou `behavior_instruction_path` (`../diretrizes/instrucoes-llm.md`, resolvido a partir de `rag/`) |
| `rag/` | ingest, pelos `sources` do projeto |

Repositório público: a pasta guarda conhecimento e casos **anonimizados**. Nunca log de
shadow, telefone, nome de pessoa, chave ou endereço de servidor. Credenciais ficam em
`local-only/credentials/` (fora do Git, [isolamento](./treinamento-llm/isolamento-e-execucao-mini62.md)).

## 3. O que passa de um projeto para outro

| Aprendizado | Passa? | Como |
|---|---|---|
| Fato, corpus, link, preço, data | **nunca** | é do projeto |
| Exemplo aprovado (`great`, [22](./22-answer-ratings.md)) | não como texto | o texto carrega fato do projeto; o que ele ensina (forma, recusa, encaminhamento) pode virar regra da casa, reescrito sem fato |
| Termo proibido aprovado | só o genérico | «já fiz sua inscrição» vale para todos; «vaga garantida na EBA» é do Bike Anjo |
| Regra de comportamento | **sim**, por padrão | sobe para `regras-da-casa.md`; quem herda é todo projeto que não a recusou |
| Tipo de caso e suas ações (`case_kind`, `allowed_actions`, [26](./26-second-opinion.md)) | como molde | «resposta a uma confirmação de presença: confirmar · liberar · passar para pessoa» serve a qualquer projeto com evento; cada um declara as suas |
| Caso de ruído (saudação, emoji, resposta automática) | sim, entre projetos do mesmo canal | o certo é silêncio em qualquer WhatsApp |
| Nota e julgamento de uma pessoa | não | julgamento é sobre a resposta daquele projeto |

## 4. Quando não passar

1. O manifesto do projeto recusa a regra (o cliente trabalha de outro jeito). A recusa
   fica escrita, com o motivo, na seção «Regras da casa que este projeto não segue».
2. A regra é de canal e o projeto não usa o canal: as de conversa por mensagem não valem
   para extração de documento ou tarefa de texto.
3. O portão do projeto que herdaria **piora**: a regra não sobe para ele.

## 5. Como um aprendizado sobe para a casa

1. Nasce no projeto (julgamento, termo proibido, opinião do professor).
2. Vira candidato quando é comportamento sem fato, ou quando o mesmo erro aparece em dois
   projetos.
3. Uma pessoa reescreve sem fato e acrescenta em `regras-da-casa.md` (é texto revisado por
   Git, como o resto da casa).
4. O portão roda em cada projeto que herda; projeto que piora ganha a recusa no manifesto,
   com o motivo.

## 6. O que o código faz hoje

| Peça | Situação |
|---|---|
| Pasta por projeto, modelo e `create_project.py` | feito |
| Casos de ouro por projeto, portão lendo de lá | feito |
| Postura do Bike Anjo em `diretrizes/` | feito; o seed lê os arquivos |
| `regras-da-casa.md` | escrito; ainda não entra sozinho no prompt: cada projeto tem a sua postura, que segue a casa. Fazer o prompt montar casa + projeto pede o portão em cada projeto ([23 § 8](./23-ecosystem-panorama.md#8-roteiro-único-do-ai2tcs)) |
| `webplace` | no formato anterior (`fluxosLLM/`, `bibliotecaConteudoLLM/`), com a instrução dentro da busca |

---

**Anterior:** [26-second-opinion.md](./26-second-opinion.md)
