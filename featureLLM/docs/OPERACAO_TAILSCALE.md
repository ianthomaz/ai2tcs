# Operação da API LLM via Tailscale (servidores e scripts)

Como consumir a API do LLM local a partir de outros dispositivos na rede Tailscale: servidores (Oracle, Linode, pcVelho) e scripts que rodam nesses ambientes. Documento do repositório **ai2tcs** (`featureLLM/docs/`); contrato HTTP geral em [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md).

**Importante:** o acesso é **interno na rede Tailscale** (entre as suas máquinas na tailnet). **Não usar Funnel** — Funnel expõe à internet pública. Aqui usamos apenas o acesso entre nós da mesma rede Tailscale (Serve ou acesso direto ao IP/nome do node).
---

## 1. Visão geral

- A API roda no **Mac mini** (host Tailscale), escutando em **localhost:28471**.
- O acesso é **só entre máquinas na rede Tailscale** (Serve ou conectando direto ao IP/nome do node). Nada é exposto à internet (sem Funnel).
- Qualquer máquina na mesma tailnet (e com permissão na ACL) acessa a API pelo **hostname Tailscale do Mac** ou pelo IP Tailscale (100.x.x.x), na porta **28471**.

**URL base (exemplo):**

- Com **Tailscale Serve** (HTTPS na tailnet): `https://<nome-do-node>.<tailnet>.ts.net/` (ex.: `https://mini62.panther-octatonic.ts.net/`). O Serve faz proxy para `http://127.0.0.1:28471`; só máquinas da sua tailnet acessam.
- Acesso direto por IP/nome (se a porta estiver acessível na rede Tailscale): `http://<mac-tailscale-name>:28471` ou `http://100.x.x.x:28471`.

---

## 2. Autenticação

Todas as requisições (exceto `/health`, se configurado sem auth) devem enviar o token:

```http
Authorization: Bearer SEU_LLM_API_TOKEN
```

- O token é gerado uma vez e configurado no Mac (`.env`: `LLM_API_TOKEN`).
- Nos servidores/scripts: guarde o token em variável de ambiente (ex.: `LLM_API_TOKEN`) ou em arquivo restrito (ex.: `~/.config/llmapi/token`), **nunca** em repositório.

---

## 3. Endpoints e uso típico

| Método | Path | Uso |
|--------|------|-----|
| GET | `/health` | Verificar se a API (e opcionalmente Ollama) está viva. |
| POST | `/ingest` | Disparar indexação/reindexação de um projeto (body: `project_id`, opcional `incremental`). |
| POST | `/ask` | Enviar pergunta; retorna `job_id` (202). |
| GET | `/status/{job_id}` | Consultar estado do job (queued/working/done/no_answer/need_more_info/failed/cancelled). |
| GET | `/result/{job_id}` | Obter resposta final e fontes (quando status for done/no_answer/need_more_info). |
| GET | `/metrics` | Métricas simples (opcional). |

Fluxo recomendado para “perguntar”:

1. `POST /ask` com `project_id` e `question` → receber `job_id`.
2. Polling em `GET /status/{job_id}` até status terminal (done, no_answer, need_more_info, failed, cancelled).
3. `GET /result/{job_id}` para obter `answer` e `sources`.

---

## 4. Exemplos a partir de um servidor (curl)

Variáveis (ajustar no servidor):

```bash
# Host do Mac na Tailscale (nome ou 100.x.x.x)
LLM_HOST="macmini"
LLM_PORT="28471"
LLM_BASE="http://${LLM_HOST}:${LLM_PORT}"
# Token (de env ou arquivo)
LLM_API_TOKEN="${LLM_API_TOKEN}"
```

**Health:**

```bash
curl -s -H "Authorization: Bearer $LLM_API_TOKEN" "$LLM_BASE/health"
```

**Ingest (reindexar projeto):**

```bash
curl -s -X POST "$LLM_BASE/ingest" \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "itcs", "incremental": true}'
```

**Perguntar e obter resultado (polling):**

```bash
# 1) Criar job
RESP=$(curl -s -X POST "$LLM_BASE/ask" \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "itcs", "question": "Como configuro o Tailscale no servidor?"}')
JOB_ID=$(echo "$RESP" | jq -r '.job_id')
echo "Job: $JOB_ID"

# 2) Poll status (ex.: a cada 15s, até 5 min)
for i in $(seq 1 20); do
  STATUS=$(curl -s -H "Authorization: Bearer $LLM_API_TOKEN" "$LLM_BASE/status/$JOB_ID" | jq -r '.status')
  echo "Status: $STATUS"
  case "$STATUS" in
    done|no_answer|need_more_info|failed|cancelled) break ;;
  esac
  sleep 15
done

# 3) Resultado
curl -s -H "Authorization: Bearer $LLM_API_TOKEN" "$LLM_BASE/result/$JOB_ID" | jq .
```

---

## 5. Scripts em outros ambientes

- **Bash:** use o padrão acima (curl + jq); guarde `LLM_API_TOKEN` em env ou arquivo seguro.
- **Python:** use `httpx` ou `requests`; base URL = `http://<tailscale-host>:28471`; header `Authorization: Bearer <token>`; loop de polling em `/status/{job_id}` com timeout global (ex.: 5 min).
- **Node/TS:** `fetch` ou `axios`; mesma base URL e header; implementar polling e depois `/result/{job_id}`.

Regras gerais:

- Timeout de rede por requisição: ex.: 30s para `/ask` e `/ingest`, 10s para `/status` e `/result`.
- Timeout total de espera: ex.: 5 min; após isso considerar falha ou cancelar (se houver endpoint de cancelamento).
- Em 4xx (token inválido, project_id inexistente): não retentar; corrigir config.
- Em 5xx ou rede: retry com backoff leve (ex.: 2–3 tentativas).

---

## 6. Fallbacks quando itcsVM não alcança Mac via Tailscale

O itcsVM usa DERP (sem conexão direta) e **não consegue abrir TCP para nenhum peer Tailscale** (mini62, pcvelho, bikeanjovm) — timeout. UDP (ping) funciona; TCP falha. BikeAnjoVM (mesma Oracle) alcança o Mac; itcsVM não. Causa provável: rede/egress do itcsVM.

### 6.1 Túnel SSH reverso (funciona para itcsVM)

Solução que funciona: **mini62 cria túnel SSH para itcsVM via IP público** (fora do Tailscale). A API fica disponível em `127.0.0.1:28471` no itcsVM.

**No mini62:**
```bash
# Túnel: itcsVM:127.0.0.1:28471 -> mini62:28471
./scripts/llm-tunnel-mini62-to-itcsvm.sh
# Deixar rodando. Ctrl+C para parar.
```

**Pré-requisitos:**
- Oracle Cloud: permitir inbound SSH (22) no itcsVM a partir do IP público do mini62
- mini62 tem chave `~/.ssh/itcsvm_key` (ou `SSH_KEY`) para itcsVM
- API rodando em mini62:28471

**No itcsVM (webplacecc):** `LLM_API_URL=http://127.0.0.1:28471`

**Persistir no mini62 (launchd):** criar `~/Library/LaunchAgents/com.itcs.llm-tunnel.plist` que executa o script em `ProgramArguments`. Usar `KeepAlive: true` e `RunAtLoad: true` para reabrir se cair.

**Teste:** no itcsVM, com o túnel rodando no mini62: `curl -s http://127.0.0.1:28471/health`

### 6.2 Proxy via pcvelho (só se itcsVM alcançar pcvelho)

O pcvelho alcança o Mac. Mas **o itcsVM não alcança o pcvelho** via Tailscale (mesmo problema TCP). O proxy só ajuda se outra VM conseguir chegar ao pcvelho.

**Setup (quando pcvelho for acessível):**
```bash
./scripts/setup-llm-proxy-pcvelho.sh
# (será pedida a senha sudo no pcvelho)
```

**Cliente:** `LLM_API_URL=http://100.89.195.56:28472` em vez de `http://100.90.214.92:28471`.

---

## 7. Tailscale no Mac (lembrete)

- API sobe em `127.0.0.1:28471`.
- No Mac: rodar `./scripts/tailscale_serve.sh` (ou `tailscale serve --bg http://127.0.0.1:28471`) para expor a API na rede Tailscale.
- No admin do Tailscale: aprovar “Serve” para este dispositivo se necessário.
- ACL: restringir quais nós podem acessar o serviço na porta 28471.

---

## 8. Referência rápida de contratos

Ver exemplos completos de request/response em `00_PLANEJAMENTO_LLM_LOCAL.md` (sec. 3. Endpoints e contrato).

Resumo:

- **POST /ask** (202): `{"project_id": "...", "question": "...", "hint": "..."}` → `job_id`, `status_url`, `result_url`.
- **GET /status/{job_id}** (200): `status`, `progress`, `created_at`.
- **GET /result/{job_id}** (200): `status`, `answer`, `sources[]`, `confidence`.
