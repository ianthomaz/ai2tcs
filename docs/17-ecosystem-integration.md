# 17 — Integração no ecossistema ITCS (hub, zap, bridge)

**Natureza:** retrato de ligações, não plano. **Cópia canónica:** `0MM_ITCS/docs/08_ecosystem_integration.md`
(hub privado). Aqui fica só a parte que interessa a quem lê este repo.

**Anterior:** [16-code-review-findings.md](./16-code-review-findings.md) · **Seguinte:** —

---

## O papel do ai2tcs no conjunto

Motor LLM/RAG único e multi-projeto. Os outros repos são **clientes HTTP**, não forks:

| Cliente | `project_id` | Rotas que usa | Biblioteca RAG (vive no repo do cliente) |
|---------|--------------|----------------|-------------------------------------------|
| `webplaceZap` (zapzap, WhatsApp) | `webplacecc` | `/router`, `/ask`, `/extract`, `/boletoExtract` | `bibliotecaLLM_webplacecc/` + `mapaFluxosLLM/` |
| `zapCursorAgent` (Ian pessoal) | `ian_zap` | `/ask`, `/router` (ver [14](./14-ian-zap-personal.md)) | `bibliotecaLLM_ian_zap/` |
| Bike Anjo, aiClaudia, estudosMobi | ver [15](./15-cross-project-fixes.md) | `/ask`, `/extract` | no repo de cada um |

Padrão já repetido: **chave por projeto** (`itcs_{project_id}_*`), `config_json` por
projeto, fontes (`{PROJECT_ID}_SOURCES`) apontando para pastas do repo cliente, `seed`
+ `ingest` para indexar.

## Fronteira de privilégio (decidido)

O canal WhatsApp (`webplaceZap`) é público e de **baixo privilégio** (entrada de qualquer
pessoa; saída também para alertas ao dono, filtrados por telefone); o canal Google Chat
-> Cursor (`zapCursorAgent`) é privado, do dono, e de privilégio máximo. A rota
WhatsApp -> Cursor descrita em [14](./14-ian-zap-personal.md) está **arquivada, não
pendente** — esse doc descreve história. O ai2tcs serve os dois lados como motor e não
detém poder de canal nenhum.

## Motores por cliente vêm aí (pedido futuro, não agendado)

O zapzap quer expor ações de projeto a partir do WhatsApp — por exemplo: cliente manda um
link de artigo, e o sistema extrai título, imagem principal e um resumo curto para
publicar na página dele. Do lado deste repo isso é **uma rota nova da família `/extract`**
(ler URL -> campos estruturados), com o `project_id` do cliente a decidir prompt e
política — não um motor separado no zap. Registado para quando houver pedido concreto:
`0MM_ITCS/docs/08_ecosystem_integration.md` §4.4.

## Ligações de infra menos óbvias

- O **Cloudflare Tunnel desta conta** serve `llm.webplace.cc` **e** `gchat.webplace.cc`
  (webhook do Google Chat do zapCursorAgent). Mexer no túnel afecta os dois.
- `llm_api` corre em mini62, a mesma máquina do bridge Cursor (`:28472`) e do adapter
  Chat (`:28473`). Portas vizinhas, produtos diferentes: `28471` é a LLM.

## O que o hub 0MM ainda não sabe deste repo

| Facto | Estado |
|-------|--------|
| `GET /health` (ollama, postgres, disco) e `GET /metrics` (jobs por estado) | Existem em `llm_api/app/api/health.py`; o hub **não os consome** — o `monitor.checks` do `itcsManifest.yaml` só sonda o apex |
| Quem consome a LLM | O contrato do hub tem bloco `spec.llm` para isso; nenhum cliente o preencheu |
| `hub.lastHarvestAt` | `null` — o ciclo de harvest nunca fechou |
| `contractVersion: "21"` no manifesto | Numeração antiga do hub; o contrato é hoje `docs/06_project_hub_contract.md` |

Nada disto é trabalho decidido — está registado para não se perder. Perguntas em
aberto e caminhos possíveis: `0MM_ITCS/docs/08_ecosystem_integration.md` §7 e §8.
