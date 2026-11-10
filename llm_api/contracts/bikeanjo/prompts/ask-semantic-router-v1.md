# Prompt / pedido ao ai2tcs — 2º roteador semântico do `/ask` (v1)

**Status (30/out):** entregue no ai2tcs e espelhado em `ask.schema.json` /
`ask.examples.json` / `ORIGIN.md` / [HANDOFF §4](../HANDOFF_AI2TCS.md). Este arquivo
fica como o pedido original (histórico). Próximo passo: executor no Bike Anjo
(`intent.action` → consulta → mensagem padrão, shadow primeiro).

Espelho de produto:
[07b § Dois roteadores](../../../07b_ZAP_FLUXOS_E_LLM.md#dois-roteadores---mecânico-ask-semântico-dono-30out2026).

---

## Contexto (Bike Anjo → ai2tcs)

No WhatsApp, o **1º roteador é mecânico no cliente** (só passa se a mensagem tiver `?`).
O **2º roteador é o `/ask`**: qualidade semântica do que a pessoa quer saber.

Hoje o `/ask` devolve sobretudo `answer` em prosa + RAG. Em perguntas do tipo
«já me inscrevi? / consegue ver aí?» o modelo inventa prosa, manda link de cadastro
ou compete com o corpus («canal não confirma vagas»). A LLM **não lê banco**. O cliente
(Bike Anjo) é quem consulta e escolhe mensagem padrão.

Precisamos que o `/ask` (genérico, multi-projeto) passe a devolver um corte estruturado
configurável, sem depender de prosa para fato de usuário.

## Pedido (genérico)

1. No resultado do `/ask` (e, se fizer sentido, do `/router`), além de `answer` / `signals`,
   devolver um bloco estruturado (nome a combinar, ex. `intent` ou `suggested_action`) com:

| Campo | Valores (Bike Anjo v1) |
|---|---|
| `knowledge_kind` | `org_general` \| `user_system` \| `unknown` |
| `action` | `null` se `org_general`; se `user_system`, um código da **lista fechada do projeto** |
| `action_payload` | objeto opcional (ex. `event_id` / `event_name` se o modelo inferir do histórico) |
| `answer` | prosa só para `org_general` (RAG); em `user_system` preferir `answer` vazio / rascunho **não** afirmativo de status |

2. A lista de `action` vem da **config do projeto** (como `text_moderation.labels`), não
   hardcoded no core. Bike Anjo, primeiro item:

- `event_interest_lookup` — a pessoa pergunta se já tem inscrição / interesse / se «você
  consegue ver» o status dela num evento.

Actions futuros (só reservar no schema / config, sem implementar agora):
`registration_completeness_lookup`, `city_event_lookup`.

3. Regras duras no prompt do projeto Bike Anjo:

- Nunca afirmar «inscrita / confirmada / na lista» em prosa.
- Nunca mandar magic link / link de cadastro quando `knowledge_kind=user_system` e
  `action=event_interest_lookup`.
- Se a pergunta for status da pessoa no sistema → `user_system` + action; **não** RAG de
  procedimento genérico de inscrição.
- Se for história / o que é Bike Anjo / como funciona a articulação → `org_general` + RAG.

## Casos de eval (mínimo)

| # | Pergunta (com histórico curto se preciso) | Esperado |
|---|---|---|
| 1 | «acho q já fiz a inscrição… vc consegue ver aí?» (contexto: convite EBA) | `user_system` + `event_interest_lookup` |
| 2 | «já me inscrevi?» | idem |
| 3 | «o que é a Bike Anjo?» | `org_general`, action null, prosa RAG |
| 4 | «como funciona a Escola Bike Anjo?» | `org_general` |
| 5 | «obrigado» / sem `?` | fora do escopo do ASK (cliente não chama); se chamado: `no_answer` / silence |
| 6 | «quero o link do cadastro» | **não** é `event_interest_lookup` (outro fluxo / geral) |

## Entrega esperada no ai2tcs

- [ ] Schema + exemplos do resultado `/ask` com o bloco estruturado
- [ ] Prompt / seed do projeto `bikeanjoall_2026` com as regras duras
- [ ] Config `actions` (lista fechada) no projeto
- [ ] Eval set com os 6 casos (pass/fail)
- [ ] Nota no ORIGIN / contrato espelhado de volta para `docs/contracts/ai2tcs/` no Bike Anjo

Quando isso existir, o Bike Anjo: lê `action` → executa consulta → mensagem padrão
(shadow primeiro). Sem isso, prosa continua errando o caso Mariana.
