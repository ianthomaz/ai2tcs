# Plano: conversas do professor por pessoa (pool, vínculo, expiração 30 dias)

Estado: **desenho** (14/nov/2026). Código atual: uma conversa por `subject_ref` no
arquivo Mac `~/.gemini/antigravity/second_opinion_teacher_state.json` (PR #12). Pool pronto,
tabela de vínculos e apagar aos 30 dias **ainda não existem**.

Contrato da fila: [26-second-opinion.md](../26-second-opinion.md).  
Ponte Antigravity: [antigravity-no-mini62.md](./antigravity-no-mini62.md).

Vocabulário neste plano:

| Termo | O que é |
|---|---|
| **Caso** | Um `POST /second-opinion` (uma mensagem a julgar) |
| **Conversa do professor** | Uma thread no Antigravity (`conversationId` + pasta `brain/<id>/`) |
| **Vínculo** | Ligação pessoa ↔ conversa (quem “possui” aquela thread) |
| **Pool pronto** | Conversas já criadas e com contexto, ainda sem dono |
| **Worker da fila** | `second_opinion_worker.py` no Mac (não confundir com a conversa) |

---

## 1. Problema

Hoje, no **primeiro** caso de cada pessoa, o runner paga na hora:

1. criar conversa (`agentapi new-conversation`) — até ~30 s  
2. esperar boas-vindas / `PLANNER_RESPONSE` — até ~30 s  
3. mandar o caso e esperar a opinião — até ~160 s  

Soma fácil **> 180 s** (`SECOND_OPINION_TIMEOUT_S`) → o caso falha por timeout.

Além disso:

- Sem limpeza, conversas e pastas `brain/` **acumulam** no Mac.
- Precisamos saber **quem** está ligado a **qual** conversa (cadastro Bike Anjo ou contato sem conta).
- Telefone/e-mail no vínculo exigem cuidado: o professor **não** deve ver o id cru no prompt (regra já do § `subject_ref`).

---

## 2. Objetivo

1. No caminho do caso: ** só **enviar mensagem + ler JSON** (conversa já pronta ou já vinculada).  
2. Manter **uma conversa por pessoa** (histórico do professor por indivíduo).  
3. **Expirar e apagar** vínculos/conversas sem uso há **30 dias**.  
4. Ter uma **lista auditável** de agentes/conversas e a quem pertencem.

---

## 3. Identidade da pessoa (chave do vínculo)

Ordem de preferência ao montar a chave estável do vínculo:

| Prioridade | Quando | Chave estável | O que o professor vê |
|---|---|---|---|
| 1 | Tem cadastro Bike Anjo | `user_id` (= `subject_ref` atual) | Nunca o id; só fatos do caso |
| 2 | Sem cadastro, tem e-mail | hash do e-mail normalizado (ex. SHA-256 truncado) | Nunca o e-mail cru |
| 3 | Sem cadastro, tem telefone | hash do telefone normalizado (E.164) | Nunca o telefone cru |
| 4 | Nada disso | `_sem_conta` (conversa geral compartilhada — só fallback) | — |

Regras:

- No **prompt** e no **título** da conversa Antigravity: **nunca** `user_id`, telefone ou e-mail.
- No **env** do runner: pode ir `SECOND_OPINION_SUBJECT_REF` (id) como hoje; hashes de contato, se existirem, também só no env/estado — não no texto do caso.
- Telefone/e-mail **brutos** se forem guardados para suporte humano, ficam só em store local/criptografada ou no sistema BA — **não** no repositório público e **não** no prompt do professor.

Nome de campo a confirmar com o dono (proposta): `subject_key` = `user:<id>` | `email_hash:<…>` | `phone_hash:<…>` | `_sem_conta`.

---

## 4. Tabela de vínculos (lista de agentes / conversas)

Precisamos de um registro explícito — não só o JSON solto do Mac — para listar, expirar e auditar.

**Proposta de lugar (a confirmar):** tabela no Postgres do ai2tcs (junto da fila `second_opinions`), porque o teto diário e os casos já vivem lá; o Mac continua dono dos arquivos `brain/`.

Nome de tabela **proposta** (confirmar antes de criar): `second_opinion_teacher_bindings`.

| Coluna (proposta) | Tipo | Papel |
|---|---|---|
| `id` | uuid / bigserial | PK |
| `project_id` | text | ex. `bikeanjoall_2026` |
| `subject_key` | text | chave estável (§ 3) |
| `subject_kind` | text | `user_id` · `email_hash` · `phone_hash` · `none` |
| `conversation_id` | text | id Antigravity |
| `status` | text | `ready` · `bound` · `expired` · `deleted` |
| `turns` | int | casos já julgados nesta conversa |
| `bound_at` | timestamptz | quando ligou à pessoa (null se `ready`) |
| `last_used_at` | timestamptz | último caso |
| `expires_at` | timestamptz | `last_used_at + 30 days` (ou `bound_at + 30 days` se nunca usou após bind — definir) |
| `created_at` | timestamptz | criação da conversa / linha |

Espelho operacional no Mac (já existe, evolui):

`~/.gemini/antigravity/second_opinion_teacher_state.json`

```text
{
  "ready": [ { "conversation_id", "created_at" } ],
  "conversations": {
    "<subject_key>": {
      "conversation_id", "turns", "bound_at", "last_used_at", "expires_at"
    }
  }
}
```

Regra: **Postgres = fonte de verdade para lista/expiração**; JSON Mac = cache rápido do runner. Se divergirem, manda o Postgres (ou o contrário — decidir na implementação).

---

## 5. Fluxo no caso (caminho quente)

```text
caso chega (com subject_ref e/ou contato hasheável)
        │
        ▼
existe vínculo bound e last_used_at dentro de 30 dias?
   sim → usa essa conversation_id
   não → pega 1 conversa do pool ready, faz bind (status=bound), grava subject_key
        │
        ▼
SendAgentMessage(caso) → poll transcript → JSON no stdout
        │
        ▼
atualiza turns, last_used_at, expires_at (= now + 30 dias)
```

Fora do caminho quente (cron / depois do caso / LaunchAgent leve):

- se `ready.length < N` → cria conversas novas, manda prompt genérico de professor, marca `ready`
- se `expires_at < now` → § 6 (expirar e apagar)

Sugestão de N: **10** prontas (mínimo); **20** se quiser cobrir o teto diário da fila.

---

## 6. Expirar e apagar (30 dias) — o ponto crítico

### 6.1 Quando expira

Uma conversa/vínculo expira se **`now > expires_at`**, com:

`expires_at = last_used_at + 30 days`  
(se ainda `ready` e nunca bound: `created_at + 30 days` para não acumular pool velho).

### 6.2 O que “apagar” significa (três camadas)

| Camada | Ação | Dono |
|---|---|---|
| A. Vínculo (tabela / JSON) | `status=expired` ou `deleted`; tira de `conversations` / `ready` | ai2tcs (worker ou job no Mac) |
| B. Disco Mac | remover ou arquivar `~/.gemini/antigravity/brain/<conversation_id>/` | script no mini62 |
| C. Hub Antigravity | apagar/arquivar a conversa na UI/API para não deixar lixo no app | **universo Antigravity** — ver § 8 |

Sem a camada C resolvida, limpar só A+B pode deixar conversas órfãs no hub; limpar só C sem A deixa o runner achar id morto.

### 6.3 Job de limpeza (proposta)

- Quem: processo no Mac (mesmo user da sessão Antigravity), periódico (ex. 1×/dia) ou após cada lote de casos.
- Passos: listar `expires_at < now` → chamar API/procedimento de delete (§ 8) → apagar `brain/<id>` se seguro → marcar linha `deleted`.
- Falha no delete do hub: **não** mentir `deleted`; ficar `expired` + retry; alertar no log.

---

## 7. O que já está feito vs o que falta

| Peça | Estado |
|---|---|
| Fila `/second-opinion` + worker + runner HTTP/JSONL | Feito |
| Uma conversa por `subject_ref` (env) + state JSON | Feito (PR #12) |
| Id fora do prompt/título | Feito |
| Pool `ready` (default 10) + reposição em background | **Feito** (`antigravity_agent_runner.py`, `--ensure-pool`) |
| Lista auditável de vínculos | **Feito no Mac** (`second_opinion_teacher_state.json`: `ready` + `conversations` + `deleted_log`). Tabela Postgres opcional — **adiada** |
| Hash e-mail/telefone sem cadastro | **Feito no runner** (`SECOND_OPINION_EMAIL_HASH` / `PHONE_HASH` ou hash de raw). Worker ainda só manda `SUBJECT_REF` + `PROJECT_ID` |
| Expiração 30 dias + delete hub | **Feito** (`expire_and_cleanup` + `DeleteCascadeTrajectory`; CLI `--expire`) |
| Delete real no Antigravity (hub) | **Feito** (§ 8 verificado no mini62) |
| Create fora do caminho quente | **Feito** (consome `ready`; create só no pool) |

---

## 8. Para o Antigravity preencher (universo dele — RESPOSTAS VERIFICADAS NO MINI62, build 2.31.2)

*Respondido e testado contra o binário real `/Applications/Antigravity.app/Contents/Resources/bin/language_server` (build 2.31.2) no mini62 em 14/nov/2026.*

### 8.1 Apagar / arquivar conversa

1. **Existe comando CLI ou RPC para apagar uma conversa por `conversationId`?**  
   **SIM.** Existe o RPC HTTP/JSON no `LanguageServerService`:
   - Endpoint: `POST http://<ANTIGRAVITY_LS_ADDRESS>/exa.language_server_pb.LanguageServerService/DeleteCascadeTrajectory`
   - Header: `x-codeium-csrf-token: <ANTIGRAVITY_CSRF_TOKEN>`
   - Body: `{"cascadeId": "<conversation_id>"}`
   - Retorno: `{}` (HTTP 200).
2. **Efeito real (testado ao vivo na conversa `bdb65355-74f3-413c-88cb-923a2bcda7d9`):**  
   Uma única chamada a `DeleteCascadeTrajectory` **apaga simultaneamente as três camadas do Antigravity**:
   - Remove a conversa da memória/hub da IDE (`conversation_summaries.db`);
   - Apaga o SQLite `~/.gemini/antigravity/conversations/<id>.db`;
   - Apaga o diretório inteiro `~/.gemini/antigravity/brain/<id>/` (incluindo `transcript.jsonl` e `transcript_full.jsonl`).
3. **Apagar só a pasta `brain/<id>/` e `.db` manualmente na mão é seguro?**  
   **Não recomendado** enquanto o RPC existir: apagar arquivos por fora com o app aberto deixa a entrada órfã no índice em memória (`conversation_summaries.db`) do hub. Usar sempre `DeleteCascadeTrajectory` (e `shutil.rmtree` apenas como fallback se sobrar pasta).
4. **Delete é permitido com o app aberto? Precisa de CSRF + `ANTIGRAVITY_LS_ADDRESS`?**  
   **Sim.** Funciona com o Antigravity.app aberto e usa exatamente o mesmo `ANTIGRAVITY_LS_ADDRESS` + `ANTIGRAVITY_CSRF_TOKEN` que o runner já descobre via `discover_language_server()`.

### 8.2 Pool e custo

5. **Criar 10 conversas “prontas” com o mesmo prompt genérico: há rate limit / custo por conversa ociosa?**  
   - **Conversa ociosa (`waiting` / parada): custo ZERO** (zero tokens, zero CPU, zero polling; fica apenas gravada em disco até receber `SendAgentMessage`).
   - **Custo na criação:** apenas 1 turno curto de boas-vindas (`flash_lite`) por conversa criada (~12k input tokens do system prompt base + ~10 output tokens). Criar 10 em sequência leva ~60–90 s no total; recomenda-se intervalo de ~1 s entre criações para não congestionar o `language_server` local.
6. **Há como clonar ou forkar uma conversa template em vez de `new-conversation` 10 vezes?**  
   Existe o RPC `/exa.language_server_pb.LanguageServerService/ForkConversation`, mas `agentapi new-conversation --model=flash_lite` fora do caminho quente (`--init-pool 10` / reposição em background) é mais simples, limpo e garante estado independente.
7. **Modelo barato recomendado para o turno de contexto e operação:**  
   `flash_lite` (`--model=flash_lite`).

### 8.3 Identidade e isolamento

8. **O motor mistura histórico entre conversas diferentes no mesmo user logado do Mac?**  
   **Não.** Cada `conversationId` tem seu próprio SQLite (`conversations/<id>.db`) e seu próprio `brain/<id>/`. A menos que uma tool de busca de conversas seja invocada (e o prompt do professor proíbe tools), uma conversa não vê o histórico de outra.
9. **Com `SendAgentMessage` + conversa reutilizada 30 dias: o modelo “lembra” turnos antigos?**  
   **Sim**, os turnos anteriores daquela mesma pessoa permanecem no contexto da conversa (inclusive aproveitando *context caching* nos tokens repetidos, como medimos: `cache_read_tokens: 10146`), até o limite de `ANTIGRAVITY_MAX_TURNS_PER_CONVERSATION` (default 40 turnos) ou 30 dias de inatividade.

### 8.4 Tabela-resumo e receita mínima de expire + delete

| Método / Operação | Existe? | Comando / RPC exato | Efeito no hub e no disco |
|---|---|---|---|
| Criar conversa para o pool (`ready`) | **Sim** | `agentapi new-conversation --model=flash_lite --title="Professor Segunda Opinião (ai2tcs)" "<INIT_PROMPT>"` | Cria thread no hub + `conversations/<id>.db` + `brain/<id>/` |
| Enviar caso para conversa vinculada (`bound`) | **Sim** | `POST /exa.language_server_pb.LanguageServerService/SendAgentMessage` `{"recipient": "<id>", "content": "..."}` | Acorda a conversa, grava resposta em `brain/<id>/.system_generated/logs/transcript_full.jsonl` |
| Verificar se conversa existe no hub | **Sim** | `POST /exa.language_server_pb.LanguageServerService/GetConversationMetadata` `{"conversationId": "<id>"}` | Retorna `{"metadata": {...}}` se viva, ou erro se apagada |
| **Apagar conversa expirada (hub + disco)** | **Sim** | `POST /exa.language_server_pb.LanguageServerService/DeleteCascadeTrajectory` `{"cascadeId": "<id>"}` | **Remove do hub da IDE + apaga `conversations/<id>.db` + apaga `brain/<id>/`** |

**Receita mínima de `expire + delete` para um `conversationId`:**
1. Chamar `rpc_post(addr, token, "DeleteCascadeTrajectory", {"cascadeId": conv_id})`.
2. Conferir com `GetConversationMetadata` (ou se `~/.gemini/antigravity/brain/<conv_id>` sumiu). Se sobrar diretório no disco, `shutil.rmtree(BRAIN_DIR / conv_id, ignore_errors=True)`.
3. Só após sucesso, remover o vínculo / marcar como `deleted` no estado (`second_opinion_teacher_state.json`). Se o RPC falhar (ex.: app fechado), manter como `expired` para tentar no próximo ciclo.

---

## 9. Ordem de implementação (ai2tcs)

| Passo | Estado |
|---|---|
| 1. Fechar § 8 (delete real) | Feito |
| 2. State JSON `ready` + `conversations` + TTL | Feito (JSON Mac; Postgres adiado) |
| 3. Pool + bind no caminho quente | Feito |
| 4. Expire + `DeleteCascadeTrajectory` | Feito (`--expire`; agendar no LaunchAgent se quiser diário) |
| 5. Hash contato no runner | Feito; worker BA pode passar hash depois |
| 6. Ligar API + projeto + worker `--listen` | Ops (ver checklist de ativação) |
| 7. Tabela Postgres de vínculos (opcional) | Adiado até o dono pedir |
| 8. Atualizar [26](../26-second-opinion.md) com pool/TTL | Pendente cosmético |

---

## 10. Fora de escopo deste plano

- Ligar/desligar `SECOND_OPINION_ENABLED` (já é ops).  
- Chave 2 Bike Anjo / `PROD_READONLY_*` (consulta de fatos; outro fio).  
- Observer `OPS_OBSERVE_TOKEN` (olho do ai2tcs; outra rota).  
- Trocar professor para Gemini REST (fallback existe; plano oficial continua Antigravity).
