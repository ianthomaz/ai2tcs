# Handoff para o ai2tcs · 17/out/2026

O que o lado Bike Anjo pede ao ai2tcs antes do próximo deploy de tudo. Quem executa é o
agente do repositório ai2tcs; daqui só se registra. Passo no deploy:
[engenharia_attention_change](../../06c_ATTENTION_CHANGE.md) (item do handoff ai2tcs).

Conferência feita contra `ai2tcs@f6fd46f` (`llm_api/contracts/bikeanjo/`), com `diff -r`.

## 1. Pacote de contratos: o espelho do ai2tcs está atrás

Esquemas e exemplos JSON são **idênticos**. Diferem os arquivos que o serviço lê em tempo
de execução e três documentos. O Bike Anjo está à frente:

| Arquivo | O que o ai2tcs tem | O que o Bike Anjo tem |
|---|---|---|
| `prompts/reply-suggest-v1.md` | sem tom de voz; link da articulação `bikeanjo.org/a/{slug}` | segue `38_tom_voz_associacao`; link `{slug}.bikeanjo.org` |
| `prompts/feedback-triage-v2.md` | diz que o v1 está em uso | v2 em uso |
| `prompts/feedback-triage-v1.md` | existe | não existe (v2 é o único) |
| `rag/retrieval-hints.json` | sem `37_shadow_aprendizado_deploy` e `38_tom_voz_associacao` | com os dois |
| `rag/corpus-manifest.json` | sem as linhas do 37 e do 38 | com as duas |
| `CHECKLIST_AI2TCS.md`, `EXPECTATIVAS.md`, `README.md`, `rag/RAG_PORTAS.md` | versão de 10/out | versão atual |

**Fazer no ai2tcs:** copiar `docs/contracts/ai2tcs/` deste repositório por cima de
`llm_api/contracts/bikeanjo/` (fora `runs/`), apagar `prompts/feedback-triage-v1.md`,
atualizar `ORIGIN.md` com o SHA da main do Bike Anjo, rodar
`tests/test_bikeanjo_ops_contract.py`. Depois do deploy do ai2tcs, `replySuggest` passa a
usar o tom de voz e o link novo.

## 2. Moderação de comentário de enquete

Ensaio de 17/out ([05 § Comentários](../../05_FUNCIONALIDADES.md)): `text_triage` não serve
para moderar (mede «precisa de atenção», não «pode ficar público»). O Bike Anjo passa a usar
`/ask` com lista fechada de rótulos (`PAUTA_COMMENT_MODERATION_SYSTEM` em
`sistemaBA/src/lib/pauta-comment-shadow-shared.ts`); acertou 8 de 9, e o nono (telefone) é
regra local.

**Pedido ao ai2tcs (genérico, sem nome de projeto):** tarefa `POST /task/text_moderation`.
O projeto configura `config_json.tasks.text_moderation.labels` (`{code, meaning}`); a
resposta é `{status, labels[], excerpt, why, model, prompt_version}` com rótulos só da
lista. Sem RAG (o `/ask` busca no índice à toa e leva 15 a 28 s). Quando existir, o Bike
Anjo troca `requestAsk` por ela em `pauta-comment-shadow.ts`.

## 3. Observação de acesso (decisão do ai2tcs)

Em 17/out, de fora (`llm.webplace.cc`), sem `Authorization`:

- `GET /health` → 200 com a lista de modelos e o disco;
- `POST /task/text_triage` → 200 com a classificação;
- `POST /ask` → 202 com `job_id`.

Com a regra de chave por projeto (token global ou chave alheia → 403), pedido **sem** chave
respondendo parece fora do desenho. Conferir no ai2tcs se é de propósito. O Bike Anjo não
mexe nisso.

## 4. 2º roteador semântico — `intent` no `/ask` (v1 · 30/out/2026)

No WhatsApp, o 1º roteador é mecânico no cliente (só passa se a mensagem tiver `?`).
O 2º é o `/ask`: qualidade semântica do que a pessoa quer saber. A LLM **não lê banco**;
perguntas do tipo «já me inscrevi? / consegue ver aí?» não devem virar prosa inventada
nem link de cadastro.

**No ai2tcs (feito):** `GET /result/{id}` devolve `intent` quando
`config_json.ask_intent.enabled`. Shape: `knowledge_kind` + `action` (lista fechada do
projeto) + `action_payload`. Em `user_system` o serviço salta o RAG e deixa `answer`
vazio. Seed `bikeanjoall_2026` inclui `event_interest_lookup` (+ duas actions reservadas)
e regras duras no `system_instruction`.

**No Bike Anjo (próximo):** ler `intent.action` → executar consulta → mensagem padrão
(shadow primeiro). Sem o executor, o contrato já existe para plugar.
