# 17 — Integração com o hub ITCS e o canal WhatsApp (mapa e backlog)

**Natureza deste doc:** mapa de **recursos** e backlog aberto. Nada aqui está
decidido — serve para que uma sessão nova perceba o que o `ai2tcs` já oferece à
restante malha, o que dele ainda não é consumido, e que opções existem.

**Repo público:** este documento não inclui IPs internos, tokens nem detalhe de
tailnet. Referências de rede vivem em `local-only/` e nos repos privados.

Documentos irmãos:
- `0MM_ITCS/docs/08_ecosystem_integration.md` — visão do hub (cópia canónica)
- `webplacecc/docs/14_integracao_ecossistema.md` — visão do canal WhatsApp

---

## 1. Papel do ai2tcs na malha

O `ai2tcs` é o **motor partilhado**: um serviço, vários projetos, isolados por
`project_id` e por chave. Não é um serviço por cliente.

Projetos com seed no repo (`llm_api/scripts/seed_*.py`):

| `project_id` | Consumidor |
|---|---|
| `webplacecc` | zapzap (WhatsApp webplace.cc) — consumidor mais pesado |
| `ian_zap` | zap pessoal, rota `cursor` via bridge — ver `14-ian-zap-personal.md` |
| `bikeanjoall_2026` | Bike Anjo (repo `bikeanjo2026all`; zap em `zapzap/flows.js`); portas exclusivas em [18](18-bikeanjo-ops-ports.md) |
| `estudosmobi`, `aiclaudia`, `webplace`, `general` | restantes |

**Consequência para integração:** qualquer projeto novo que queira LLM não precisa
de infra nova — precisa de `project_id`, chave e `sources`. É o caminho mais barato
da malha, e é por isso que vale mantê-lo documentado como recurso, não como produto
isolado.

---

## 2. Superfícies que o ai2tcs já oferece

| Superfície | O quê | Estado |
|---|---|---|
| `GET /health` | Checks reais: Ollama (+modelos), Postgres, disco livre. `status: ok\|degraded` | [ x ] |
| `GET /metrics` | Texto no estilo Prometheus: totais, 24h, por estado, por projeto, duração média, STT. Se a base falha, o corpo é `llm_api_ready 0` e o HTTP continua 200 | [ x ] |
| `POST /ask` | Pergunta com RAG, assíncrono com polling | [ x ] |
| `POST /router` | Decisão de rota antes de responder | [ x ] |
| `POST /extract` | Extração de campo a partir de texto livre | [ x ] |
| `POST /ingest` | Indexação por projeto | [ x ] |
| Auth dupla | Token global **ou** chave por projeto (`app/auth.py`), com verificação de que a chave bate com o `project_id` do body | [ x ] |

### 2.1 O detalhe que interessa ao hub

`GET /health` **não é um `200` vazio** — devolve o estado de cada dependência:

```json
{ "status": "degraded",
  "checks": { "ollama": {"status": "unreachable"},
              "postgres": {"status": "ok"},
              "disk": {"status": "ok", "free_gb": 41.2} } }
```

Isto é exactamente o que uma monitorização útil precisa. **E hoje não é usado:**
o `monitor.checks` no `itcsManifest.yaml` deste repo só verifica `expectStatus: 200`
no apex. Um Ollama em baixo dá `degraded` no corpo e `200` no estado — **sonda verde,
serviço partido**.

---

## 3. O que o hub ainda não consome

- [ ] `/health` rico em vez de `200` no apex (`monitor.checks` deste repo)
- [ ] `/metrics` — jobs por projeto/estado dariam um painel de uso quase de graça
- [ ] `spec.envs` deste manifesto não declara `port` nem `pathRemote` (o do
      `webplaceZap` declara) — assimetria que trava automação que leia envs
- [ ] `hub.lastHarvestAt` continua `null`: o cartão existe, o hub nunca o leu

---

## 4. `spec.llm` — o bloco que os filhos deviam declarar

O contrato do hub (`0MM_ITCS/docs/06_project_hub_contract.md`) define um bloco
`spec.llm` para todo projeto que consome esta API:

```yaml
spec:
  llm:
    enabled: true
    projectId: webplacecc        # = project_id no Postgres do ai2tcs
    profile: factual             # factual | sales | creative
    ragMode: optional            # off | optional | required
    ingestPaths:
      - bibliotecaLLM_webplacecc/
```

**Estado:** o `webplaceZap` consome esta API de forma intensiva e **não declara o
bloco**. Enquanto isso durar, não há forma de o hub responder "que projetos dependem
da LLM?" sem ler código.

Valor para este repo: a lista de consumidores deixaria de viver só nos `seed_*.py`.

---

## 5. Onde o ai2tcs entra no tema "canal de aviso"

Dois papéis distintos, que convém não misturar:

**5.1 Como sistema monitorizado.** O `ai2tcs` é um dos serviços cuja queda deve
gerar aviso. Hoje a sonda é rasa (§2.1). É a ligação mais directa e barata.

**5.2 Como enriquecedor do aviso (especulativo).** Um alerta que chega ao WhatsApp
pode ser respondido; a resposta pode ir ao `/ask` com contexto do incidente. É
atraente e é **o mais distante** — depende do canal existir e estar estável primeiro,
e tem um risco próprio: se a LLM estiver em baixo, o canal de diagnóstico cai junto
com o que devia diagnosticar. Fica registado, não planeado.

---

## 6. Backlog

- [ ] `monitor.checks` a apontar para `/health` e a validar `status: "ok"` no corpo
- [ ] Declarar `port` e `pathRemote` em `spec.envs` (alinhar com o BD, não adivinhar)
- [ ] Documentar `/metrics` em `02-api-integration.md` como superfície de monitorização
- [ ] Endpoint ou nota que liste `project_id` activos (hoje só se sabe pelos seeds)
- [ ] Confirmar `spec.llm` do `webplacecc` com o dono do repo do zap
- [ ] Rever `06-edu-contract.md` e `12-llm-fleet-rag-operations.md` face ao estado actual

---

## 7. Perguntas em aberto

- [ ] `/health` e `/metrics` devem ficar públicos (para o hub sondar sem chave) ou atrás de token? Hoje os dois respondem sem Bearer; o middleware de sessão só cobre `/dashboard`.
- [ ] O `degraded` do `/health` deve devolver `200` ou `503`? Hoje é `200` — decide se a sonda do hub precisa de ler o corpo.
- [ ] A lista de projetos activos deve sair para o catálogo do hub, ou fica só aqui?

---

**Anterior:** [16-code-review-findings.md](./16-code-review-findings.md) · **Seguinte:** [18-bikeanjo-ops-ports.md](./18-bikeanjo-ops-ports.md)
