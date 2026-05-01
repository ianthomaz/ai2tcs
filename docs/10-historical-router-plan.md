# 10 — Plano histórico (fleet, router, chaves, ingest)

**Data:** abril/2026 (reescrita)
**Status:** [ ] Planejamento — decisões de produto **actualizadas** (ver § 10)
**Âmbito:** uso **estritamente local / pessoal** — sem cobrança, sem pressão comercial; migração lenta e manual, em passos independentes.
**Relacionado:** [refs/operacao-tailscale.md](./refs/operacao-tailscale.md), [02-api-integration.md](./02-api-integration.md), [09-model-upgrade.md](./09-model-upgrade.md), [UPGRADES.md](../llm_api/UPGRADES.md), `app/api/message_router.py`, `app/config.py`, `prisma/schema.prisma`.

---

## 1. Objetivo e âmbito

Evoluir a API em quatro frentes complementares:

1. **Fleet de 4 LLMs** — integrar os dois modelos novos (`deepseek-r1:8b`, `qwen2.5:7b-instruct`) ao lado dos dois já configurados (`llama3:8b`, `qwen2.5:14b-instruct`).
2. **Router "triage-first"** — o modelo rápido recebe sempre primeiro, tenta responder, e quando não faz sentido deixa uma observação interna que o router usa para escalar ao especialista certo. Inclui heurísticas de auto-selecção quando o cliente não indica modelo.
3. **Ingest partilhado + upload multipart** — biblioteca referenciável por slug entre projetos e endpoint para enviar ficheiros via HTTP.
4. **ADM** — chaves API por projeto no painel + atribuição de LLMs preferidas por projeto.

Mantém-se tudo o que já foi decidido: transição suave (token global e chaves por projeto coexistem), chamada directa ao Ollama em `127.0.0.1` continua permitida para dev, sem SLA comercial.

---

## 2. Estado actual vs. alvo

| Área | Hoje | Alvo |
|---|---|---|
| Modelos configurados | 2 (`fast=llama3:8b`, `smart=qwen2.5:14b-instruct`) em `app/config.py:15-17` | 4 (`fast`, `compact`, `smart`, `reasoner`) |
| Modelos *novos* adicionados ao Ollama mas não-cabeados | `deepseek-r1:8b`, `qwen2.5:7b-instruct` — ausentes do `.env.example`, `config.py`, `setup.sh`, testes | Totalmente integrados |
| `POST /router` | Classifica intenção WhatsApp em 7 rotas fixas (`app/api/message_router.py:31-47`) | Triage genérico: devolve `{answer?, escalate_to?, obs, task_type, confidence}` |
| Paralelismo | Worker pool único genérico (`app/jobs/worker.py:281`) | Pool por alias + warm-up especulativo + fan-out opcional em `/extract-multi` |
| Auth | `LLM_API_TOKEN` global único (`app/auth.py:10-16`) | Chaves por projeto com hash em BD; token global mantido em paralelo |
| Ingest | Só por pastas do disco (`app/api/ingest.py:24-44`); Chroma isolado em `data/<project_id>/` | `POST /ingest/upload` multipart + bibliotecas partilhadas por slug |
| Selecção de modelo por projeto | Não existe; global ou override por request | `config_json.llm_options` define alias preferido por rota, por projeto |
| Painel ADM | CRUD de projetos (`app/dashboard/routes.py`) | + CRUD de chaves + selector de LLMs preferidas |

---

## 3. Fleet de LLMs — 4 modelos, 4 aliases

| Alias | Modelo Ollama | Papel | Tamanho |
|---|---|---|---|
| `fast` | `llama3:8b` | Triage sempre-primeiro, classificação, respostas triviais, chat educacional curto | 8B |
| `compact` | `qwen2.5:7b-instruct` **(novo)** | Extracção JSON, `/edu/chat` estruturado, respostas médias quando `smart` é exagero | 7B |
| `smart` | `qwen2.5:14b-instruct` | RAG profundo, NF, respostas longas fundamentadas | 14B |
| `reasoner` | `deepseek-r1:8b` **(novo)** | Raciocínio passo-a-passo, debugging, lógica, perguntas com "porquê", cadeia causal | 8B |

### 3.1 Alterações concretas para cabear os modelos novos

- `app/config.py:15-17` → acrescentar:
  ```python
  ollama_compact_model: str = "qwen2.5:7b-instruct"
  ollama_reasoner_model: str = "deepseek-r1:8b"
  ```
- `app/config.py:56-66` → `get_model_name(alias)` passa a reconhecer `"compact"` e `"reasoner"` além de `"fast"`/`"smart"`.
- `.env.example:20-21` → acrescentar `OLLAMA_COMPACT_MODEL` e `OLLAMA_REASONER_MODEL` (comentados, com defaults).
- `scripts/setup.sh:161` → `ollama pull qwen2.5:7b-instruct && ollama pull deepseek-r1:8b`.
- `tests/test_dual_llm.py` → renomear para `tests/test_llm_fleet.py`; cobrir resolução dos 4 aliases e fallback.
- [02-api-integration.md](./02-api-integration.md) — documentar que `model` no body aceita os 4 aliases.

### 3.2 Compatibilidade

Código existente que chama `settings.get_model_name(body.model, default_alias="fast"|"smart")` continua a funcionar. Nenhum endpoint muda contrato hoje — os aliases novos só são usados quando o cliente pede ou o router os escolhe (§ 4.2).

---

## 4. Router triage-first + escalation (núcleo do plano)

### 4.1 Fluxo

```
Pedido do cliente
     │
     ▼
┌─────────────────────┐
│  fast (llama3:8b)   │   Prompt de triage → JSON estruturado
│  triage único call  │
└──────────┬──────────┘
           │
   ┌───────┴────────────────────────────┐
   │                                    │
answer_now                         escalate
   │                                    │
   ▼                                    ▼
devolve resposta             router escolhe alias
do fast ao cliente           (cliente indicou OU heurísticas § 4.2)
                                         │
                                         ▼
                                ┌──────────────────┐
                                │ compact / smart /│  recebe {pergunta, obs_do_fast}
                                │ reasoner         │
                                └──────────────────┘
```

Contrato do JSON do fast (extensão de `app/api/message_router.py:31-47`):

```json
{
  "action": "answer_now | escalate",
  "answer": "...",                  // se action=answer_now
  "escalate_to": "compact|smart|reasoner|auto",  // se action=escalate
  "obs": "nota curta para o especialista (o que já percebi, o que preciso)",
  "task_type": "chitchat|extract|rag_deep|reasoning|classification",
  "confidence": 0.0
}
```

Se o cliente enviou `model` no body, esse valor **ganha** sobre `escalate_to`. O campo `obs` é sempre passado ao especialista como parte do contexto do system prompt, para que o especialista não comece do zero.

### 4.2 Heurísticas de auto-selecção

Aplicadas quando `escalate_to="auto"` (fast não teve certeza do alvo) ou quando o cliente não indicou modelo:

| Sinal | Alias escolhido |
|---|---|
| `task_type=reasoning` ou prompt contém "porquê", "calcula", "demonstra", "passo a passo", cadeia lógica | `reasoner` |
| `task_type=extract` ou `classification`, ou schema JSON presente no prompt, ou endpoint é `/extract*` | `compact` |
| `task_type=rag_deep`, contexto retrieve com >2k tokens, ou `project.config_json.policies.prefer_smart=true` | `smart` |
| `task_type=chitchat|greeting|ack` e `confidence≥0.75` | `fast` responde directo (`answer_now`) |

Heurísticas vivem em `app/router/selection.py` (novo) — função pura e testável.

### 4.3 Paralelismo prático

Três pontos, em ordem de impacto:

1. **Warm-up especulativo.** Assim que o fast emite `task_type`, o router dispara em background um `ollama /api/generate` com `keep_alive=5m` no modelo mais provável. Quando o especialista for chamado de facto, o modelo já está quente (poupa 2-5s em cold start de 14B).
2. **Worker pool por alias.** `app/jobs/worker.py` passa a ler `LLM_WORKERS_JSON={"fast":2,"compact":1,"smart":1,"reasoner":1}` em vez de ter um pool único. Cada worker consome só jobs marcados com o seu alias. Evita que um job lento de `smart` bloqueie jobs rápidos de `fast`.
3. **Fan-out opcional em `/extract-multi`.** Campos independentes correm em paralelo contra modelos diferentes quando `project.config_json.llm_options.parallel_fields=true`. Implementação com `asyncio.gather` em `app/api/extract.py:240`. Por omissão fica desligado.

**Fora do MVP** (mencionado só para clareza): fan-out com votação/juiz entre múltiplos modelos para a mesma pergunta; router especulativo que corre `fast` e `smart` em paralelo desde o início. Entram em iteração posterior se houver evidência.

---

## 5. Chaves por projeto e painel ADM

### 5.1 Modelo de dados

Novo modelo Prisma em `prisma/schema.prisma`:

```prisma
model ProjectApiKey {
  id          String    @id @default(uuid())
  projectId   String
  keyHash     String    @unique
  label       String?
  createdAt   DateTime  @default(now())
  revokedAt   DateTime?
  lastUsedAt  DateTime?
  project     Project   @relation(fields: [projectId], references: [projectId])
}
```

- Uma chave activa por projeto é o caso comum — a BD permite várias, mas o painel destaca a última não-revogada.
- Sem rotação automática; revogação manual no painel.
- Formato da chave: `itcs_<project_slug>_<24hex>`; guardamos só `sha256(key)`.

### 5.2 Middleware dual

`app/auth.py` evolui para:

1. Se `Authorization: Bearer <k>` bate com `keyHash` → identifica projeto, segue.
2. Senão, se `k == settings.llm_api_token` (global) → identifica projeto pelo `project_id` do body/query (fluxo actual), segue.
3. Senão → 401.

A convivência dá-te liberdade para migrar cada cliente no teu tempo.

### 5.3 Dashboard

Em `app/dashboard/routes.py`, acrescentar:

- `GET /dashboard/projects/{id}/keys` — lista chaves do projeto.
- `POST /dashboard/projects/{id}/keys` — gera chave nova (mostra uma única vez no ecrã).
- `POST /dashboard/projects/{id}/keys/{key_id}/revoke` — marca `revokedAt`.
- Selector de LLMs preferidas no formulário do projeto (§ 6 abaixo e § 9 E9).

Projeto público mantém chave própria (decisão já acordada — § 10 D2).

---

## 6. Ingest partilhado e upload multipart

### 6.1 Biblioteca partilhada entre projetos

Novo modelo Prisma:

```prisma
model SharedLibrary {
  id          String   @id @default(uuid())
  slug        String   @unique
  name        String
  sources     String[]
  configJson  Json?
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
}
```

- Projetos referenciam bibliotecas partilhadas em `Project.config_json.shared_libraries: ["infra-tailscale", "webplace-dev-notes"]`.
- Cada `SharedLibrary` tem o seu próprio Chroma em `data/_shared/<slug>/chroma`.
- `app/rag/retrieve.py:15-60` estende-se: o worker consulta o Chroma do projeto **e** de cada biblioteca partilhada referenciada; resultados entram no mesmo top-k global, com campo extra `origin=project|shared:<slug>` em cada chunk (útil para citação).

Embeddings são calculados **uma vez** por biblioteca partilhada, não N vezes por projeto que a referencia — é o ganho principal.

### 6.2 Endpoint `POST /ingest/upload`

Novo handler em `app/api/ingest.py`:

- `multipart/form-data` com `file` (obrigatório), `project_id` **ou** `library_slug` (exclusivos), `subpath` (opcional, default `uploads/`).
- Grava em `project_library/<project_id>/uploads/` ou `project_library/_shared/<library_slug>/uploads/`.
- Dispara o mesmo job de ingest que já existe (`run_ingest`) — nada muda no chunking.
- Aceita `.md`, `.txt`, `.pdf`, `.json`, limite `INGEST_UPLOAD_MAX_BYTES` (default 10 MB).

**Fora do MVP:** dedup por hash entre projetos, versionamento/rollback, auditoria de uploads. Entram só se vier a fazer falta.

---

## 7. Gateway Tailscale e acesso local

Sem mudança de rumo em relação à versão anterior do plano:

- **Gateway** = camada à frente (reverse proxy ou pequeno serviço) onde o tráfego Tailscale centraliza auth e logs.
- **API FastAPI** continua a implementar os endpoints em `127.0.0.1:28471`.
- **Local / dev** pode chamar API directo ou Ollama directo em `127.0.0.1:11434` — sem obrigar o caminho do gateway.
- Escolha nginx vs serviço dedicado fica para a implementação; healthcheck pass-through em `/health`.
- **`POST /router`** é intent-classification (triage § 4), não gateway — nomes distintos para evitar confusão.

Ver [refs/operacao-tailscale.md](./refs/operacao-tailscale.md) para detalhes de rede.

---

## 8. Manual de reintegração

Novo documento [03-api-reintegration.md](./03-api-reintegration.md) (ou secção dedicada em [02-api-integration.md](./02-api-integration.md)) com:

- Contrato novo de autenticação (header, fallback para token global).
- Como mapear projeto antigo → chave nova **quando quiseres**; sem data de corte.
- Exemplos de chamada **antes/depois** para `/ask`, `/router`, `/extract`, `/ingest/upload`.
- Novos aliases disponíveis (`compact`, `reasoner`) e quando cada um faz sentido.
- Troubleshooting (401 por chave revogada, 403 por chave de outro projeto, 413 por upload grande, 503 com hint de cold start).

---

## 9. Entregáveis ordenados por dependência

| ID | Entrega | Depende de |
|----|---------|-----------|
| E1 | `config.py` + `.env.example`: aliases `compact` e `reasoner` | — |
| E2 | `ollama pull` dos dois modelos novos no mini; smoke test em `tests/test_llm_fleet.py` | E1 |
| E3 | Triage-first JSON: estender `app/api/message_router.py` para emitir `{action, answer?, escalate_to?, obs, task_type, confidence}` | E1 |
| E4 | Heurísticas de auto-selecção em `app/router/selection.py` + testes unitários | E3 |
| E5 | Worker pool por alias + warm-up especulativo em `app/jobs/worker.py` | E2 |
| E6 | Modelo Prisma `ProjectApiKey` + migração | — |
| E7 | Middleware dual em `app/auth.py` (token global + chave por projeto) | E6 |
| E8 | Dashboard: CRUD de chaves | E7 |
| E9 | `project.config_json.llm_options` com aliases preferidos por rota + UI no dashboard | E1, E8 |
| E10 | Modelo Prisma `SharedLibrary` + retrieve multi-índice em `app/rag/retrieve.py` | — |
| E11 | `POST /ingest/upload` multipart | E10 |
| E12 | [03-api-reintegration.md](./03-api-reintegration.md) + atualização de [01-overview.md](./01-overview.md) e [02-api-integration.md](./02-api-integration.md) | E7, E8, E11 |

Os blocos **(E1-E2-E3-E4-E5)**, **(E6-E7-E8)**, **(E10-E11)** e **(E9)** são independentes entre si — podes atacá-los por ordem de apetite.

---

## 10. Decisões acordadas (actualizadas)

Herdadas da versão anterior:

1. **Projeto público e `/router`:** durante a transição, permitir `/ask` e `/router` em conjunto; apertar depois.
2. **API vs gateway:** não distinguir "dois produtos" logo; foco é tráfego Tailscale passar por sítio com logs fáceis; local fica flexível.
3. **Chaves:** uma chave por projeto, sem rotação automática, projetos existentes mantêm credencial actual.
4. **Local:** API em `localhost` + Ollama directo em `127.0.0.1` permitidos para dev.
5. **Migração / prazos:** 100% pessoal, sem SLA comercial; manual de reintegração serve clareza, não pressão.

Novas (reescrita abril/2026):

6. **Fleet passa a 4 aliases:** `fast`, `compact`, `smart`, `reasoner`. Os dois novos modelos (`deepseek-r1:8b`, `qwen2.5:7b-instruct`) são cabeados via aliases novos, não substituindo os antigos.
7. **Triage-first é o padrão.** `fast` recebe sempre primeiro, decide se responde ou escala; o router usa a `obs` do fast como contexto do especialista.
8. **Auto-selecção existe.** Quando o cliente não indica modelo, heurísticas (§ 4.2) escolhem o alias a partir do `task_type` do fast.
9. **Fan-out/consenso e router especulativo ficam fora do MVP** — só warm-up, pool-por-alias e fan-out opcional em `/extract-multi` entram agora.
10. **Ingest partilhado = bibliotecas por slug + upload multipart.** Dedup por hash, versionamento e auditoria ficam fora do MVP.
11. **ADM:** chaves por projeto no painel + selecção de LLMs preferidas por projeto entram; multi-utilizador com papéis e audit log ficam fora do MVP.

---

## 11. Verificação end-to-end

Como validar cada bloco assim que for implementado:

- **E1-E2 (fleet):** `ollama list` mostra os 4 modelos; `pytest tests/test_llm_fleet.py` passa; `curl POST /ask -d '{"project_id":"webplace","question":"oi","model":"compact"}'` devolve resposta do `qwen2.5:7b`.
- **E3-E5 (router):** `curl POST /router` com "obrigado" → `action=answer_now`; com "porque é que a ingest demora mais no webplace do que no bikeanjo?" → `action=escalate, escalate_to=reasoner`. Medir latência antes/depois do warm-up.
- **E6-E8 (chaves):** criar chave no `/dashboard/projects/webplace/keys`; `curl -H "Authorization: Bearer <chave>"` para endpoint do webplace → 200; com a mesma chave contra `project_id=bikeanjoall_2026` → 403; revogar chave → 401. Token global continua a funcionar com `project_id` no body.
- **E9 (aliases por projeto):** definir `llm_options.rag_alias=reasoner` no webplace; `/ask` usa `deepseek-r1:8b` nesse projeto e `qwen2.5:14b-instruct` no bikeanjo.
- **E10-E11 (ingest):** `curl -F "file=@notas.md" "http://.../ingest/upload?project_id=webplace"` → 202, job concluído; `/ask` encontra trecho do ficheiro. Criar `SharedLibrary` `infra-tailscale`; referenciar em dois projetos; `/ask` num projeto devolve chunks com `origin=shared:infra-tailscale`.
- **E12 (docs):** `03-api-reintegration.md` existe, linkado em `01-overview.md`; exemplos curl funcionam como descritos.

---

## 12. Histórico

| Data | Nota |
|------|------|
| abr/2026 | Plano inicial: chaves, público, dashboard, roteador Tailscale, local, manual. |
| abr/2026 | Secção 6: decisões após feedback — transição suave, uma chave/projeto, local flexível, sem SLA comercial. |
| abr/2026 | **Reescrita:** integrados 2 modelos novos (`deepseek-r1:8b`, `qwen2.5:7b-instruct`), arquitectura router triage-first com heurísticas de auto-selecção, paralelismo prático (warm-up + pool por alias + fan-out opcional), ingest partilhado por slug + upload multipart, `llm_options` por projeto no painel ADM. Entregáveis expandidos para E1-E12 com dependências explícitas. |

---

**Anterior:** [09-model-upgrade.md](./09-model-upgrade.md) · **Seguinte:** — (volta a [01-overview.md](./01-overview.md))
