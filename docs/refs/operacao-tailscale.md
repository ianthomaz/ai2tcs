# Operação via Tailscale

Índice `refs/`: [README.md](./README.md). Contrato HTTP: [02-api-integration.md](../02-api-integration.md).

Consumo da API a partir de nós na **mesma tailnet**.

**llm_server:** host da API, porta **28471**.

**Tailscale:** uso **interno** à tailnet. **Proibido Funnel** para expor esta API à Internet pública.

---

## 1. Visão geral

- A API escuta em **127.0.0.1:28471** no **llm_server**.
- Outros nós na tailnet acedem pelo **hostname Tailscale** ou IP **100.x.x.x** na porta **28471** (se ACL e firewall permitirem).

**URL base (exemplos):**

- Com **Tailscale Serve** (HTTPS na tailnet): `https://<nome-do-node>.<tailnet>.ts.net/` — o Serve faz proxy para `http://127.0.0.1:28471`.
- Acesso direto: `http://<hostname-ou-IP-tailnet>:28471`.

---

## 2. Autenticação

```http
Authorization: Bearer SEU_LLM_API_TOKEN
```

- Token no `.env` do **llm_server** (`LLM_API_TOKEN`).
- Nos clientes: variável de ambiente ou ficheiro restrito — **nunca** no repositório.

---

## 3. Endpoints e uso típico

| Método | Path | Uso |
|--------|------|-----|
| GET | `/health` | API / Ollama vivos |
| POST | `/ingest` | Reindexar projeto |
| POST | `/ask` | Pergunta → `job_id` (202) |
| GET | `/status/{job_id}` | Estado do job |
| GET | `/result/{job_id}` | Resposta final |
| GET | `/metrics` | Métricas (opcional) |

Fluxo: `POST /ask` → poll `GET /status/{job_id}` → `GET /result/{job_id}`.

---

## 4. Exemplos a partir de um servidor (curl)

```bash
LLM_HOST="<hostname-ou-100.x.x.x-no-llm_server>"
LLM_PORT="28471"
LLM_BASE="http://${LLM_HOST}:${LLM_PORT}"
LLM_API_TOKEN="${LLM_API_TOKEN}"
```

```bash
curl -s -H "Authorization: Bearer $LLM_API_TOKEN" "$LLM_BASE/health"
```

(Ver [02-api-integration.md](../02-api-integration.md) para payloads completos de `/ask` e `/ingest`.)

---

## 5. Scripts em outros ambientes

- **Python:** `httpx` / `requests`; base `http://<tailscale-host>:28471`; polling com timeout global.
- **Node:** `fetch` / axios; mesma ideia.

Timeouts sugeridos: 30s por pedido em `/ask`, até ~5 min no total para o job.

---

## 6. Fallbacks quando uma VM em cloud não alcança o **llm_server** via Tailscale

Algumas VMs (especialmente atrás de DERP sem caminho TCP estável) **não abrem TCP** até certos peers — sintoma: timeout em `curl` para `100.x.x.x:28471`, enquanto ICMP pode funcionar. IPs e hosts concretos: `local-only/`.

### 6.1 Túnel SSH reverso

No **llm_server**, manténs um túnel para a VM: o script do repositório é `llm_api/scripts/llm-tunnel-api-host-to-itcsvm.sh` (a partir da raiz do clone ou de `llm_api/`); define `ITCSVM_IP`, `ITCSVM_USER`, `SSH_KEY` no ambiente (env ou `local-only/docs/`). Na VM, após o túnel, usa `LLM_API_URL=http://127.0.0.1:28471`.

**Pré-requisitos:** SSH (22) na VM acessível a partir do **llm_server**; chave SSH configurada; API a ouvir em `:28471` no **llm_server**.

**Persistência:** no macOS, `LaunchAgent` a invocar o script (ver comentários no script / notas em `local-only/`).

### 6.2 Proxy nginx noutro nó da tailnet (opcional)

Se precisares de um nó intermédio (ex.: VM sem TCP estável até o **llm_server**), podes subir nginx na tailnet que escuta numa porta (ex. 28472) e faz `proxy_pass` para o **llm_server** `:28471`. Modelo genérico: [`docs/refs/nginx/bikeanjovm.conf`](./nginx/bikeanjovm.conf) (adaptar host, IP e paths à mão). O cliente usa então `http://<IP-tailnet-do-proxy>:<porta>`. Detalhes reais: `local-only/`.

---

## 7. Tailscale no **llm_server**

- `127.0.0.1:28471` com a API a correr no **llm_server**.
- `./scripts/tailscale_serve.sh` ou `tailscale serve --bg http://127.0.0.1:28471`.
- ACL: restringir quem acede à porta **28471**.

---

## 8. Referência de contratos

Detalhe de request/response: [02-api-integration.md](../02-api-integration.md).

Resumo:

- **POST /ask** (202): `job_id`, URLs de status/result.
- **GET /status/{job_id}**, **GET /result/{job_id}**: ver manual.
