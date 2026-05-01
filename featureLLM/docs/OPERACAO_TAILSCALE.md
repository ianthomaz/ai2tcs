# Operação da API LLM via Tailscale (servidores e scripts)

Como consumir a API LLM a partir de outros dispositivos na **mesma tailnet**. Documento **ai2tcs** (`featureLLM/docs/`); contrato HTTP em [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md).

**Importante:** acesso **interno** na Tailscale. **Não usar Funnel** para expor a API à internet pública.

---

## 1. Visão geral

- A API escuta em **127.0.0.1:28471** no host onde corre.
- Outros nós na tailnet acedem pelo **hostname Tailscale** ou IP **100.x.x.x** na porta **28471** (se ACL e firewall permitirem).

**URL base (exemplos):**

- Com **Tailscale Serve** (HTTPS na tailnet): `https://<nome-do-node>.<tailnet>.ts.net/` — o Serve faz proxy para `http://127.0.0.1:28471`.
- Acesso direto: `http://<hostname-ou-IP-tailnet>:28471`.

---

## 2. Autenticação

```http
Authorization: Bearer SEU_LLM_API_TOKEN
```

- Token no `.env` do host da API (`LLM_API_TOKEN`).
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
LLM_HOST="<hostname-ou-100.x.x.x-no-host-da-api>"
LLM_PORT="28471"
LLM_BASE="http://${LLM_HOST}:${LLM_PORT}"
LLM_API_TOKEN="${LLM_API_TOKEN}"
```

```bash
curl -s -H "Authorization: Bearer $LLM_API_TOKEN" "$LLM_BASE/health"
```

(Ver [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md) para payloads completos de `/ask` e `/ingest`.)

---

## 5. Scripts em outros ambientes

- **Python:** `httpx` / `requests`; base `http://<tailscale-host>:28471`; polling com timeout global.
- **Node:** `fetch` / axios; mesma ideia.

Timeouts sugeridos: 30s por pedido em `/ask`, até ~5 min no total para o job.

---

## 6. Fallbacks quando uma VM em cloud não alcança o host da API via Tailscale

Algumas VMs (especialmente atrás de DERP sem caminho TCP estável) **não abrem TCP** até certos peers — sintoma: timeout em `curl` para `100.x.x.x:28471`, enquanto ICMP pode funcionar. O padrão é **não documentar IPs reais neste repo**; guarda-os em `local-only/`.

### 6.1 Túnel SSH reverso

No **host onde a API corre**, manténs um túnel para a VM: o script do repositório é `featureLLM/scripts/llm-tunnel-mini62-to-itcsvm.sh` (nome histórico; funciona a partir da raiz do clone ou de `featureLLM/`). Na VM, após o túnel, usa `LLM_API_URL=http://127.0.0.1:28471`.

**Pré-requisitos:** SSH (22) na VM acessível a partir do host da API; chave SSH configurada; API a ouvir em `:28471` no host de origem.

**Persistência:** no macOS, `LaunchAgent` a invocar o script (ver comentários no script / notas em `local-only/`).

### 6.2 Proxy noutro nó da tailnet

Se um nó intermédio na tailnet consegue falar com o host da API e com o cliente, podes usar `featureLLM/scripts/setup-llm-proxy-pcvelho.sh` (ajusta hostname — script é exemplo). O cliente aponta para **`http://<IP-do-proxy-na-tailnet>:28472`** (ou a porta que configurares). Valores reais: `local-only/`.

---

## 7. Tailscale no host da API

- `127.0.0.1:28471` com a API a correr.
- `./scripts/tailscale_serve.sh` ou `tailscale serve --bg http://127.0.0.1:28471`.
- ACL: restringir quem acede à porta **28471**.

---

## 8. Referência de contratos

Detalhe de request/response: [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md).

Resumo:

- **POST /ask** (202): `job_id`, URLs de status/result.
- **GET /status/{job_id}**, **GET /result/{job_id}**: ver manual.
