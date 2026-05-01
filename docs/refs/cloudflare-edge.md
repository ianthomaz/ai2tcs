# Cloudflare em `llm.webplace.cc` (edge)

Contrato HTTP da API: [../02-api-integration.md](../02-api-integration.md). Topologia e decisões táticas (túnel, equipa CF, credenciais): **`local-only/docs/CF_CLOUDFLARE_TACTICAL.md`** no teu clone (gitignored).

---

## Nomenclatura

| Nome | O quê |
|------|--------|
| **Tailscale Funnel** | Expor serviço **Tailscale** à Internet pública. Caminho alternativo ao domínio na Cloudflare. |
| **Cloudflare Tunnel** (`cloudflared`) | Tráfego Internet → edge Cloudflare → túnel → processo `cloudflared` no teu lado → `127.0.0.1` / nginx. |

O DNS público (`llm.webplace.cc`) resolve na **edge Cloudflare**. O destino interno da API continua no **llm_server**.

---

## TLS em `llm.webplace.cc` (browser → Google OAuth)

1. **Cloudflare (zona do domínio)**  
   - Registo `llm` (ou CNAME) **proxied** (nuvem laranja).  
   - **SSL/TLS** → modo **Full** ou **Full (strict)** conforme a origem tiver certificado válido ou não.  
   - **Always Use HTTPS** na zona, se aplicável.

2. **Google Cloud Console** (cliente OAuth **Aplicação Web**)  
   - **Origens JavaScript autorizadas:** `https://llm.webplace.cc`  
   - **URIs de redireccionamento autorizados:** `https://llm.webplace.cc/dashboard/auth/google/callback`  
   - Opcional (dev): `http://127.0.0.1:28471` e `http://127.0.0.1:28471/dashboard/auth/google/callback`.

3. **`llm_api/.env`**  
   - `DASHBOARD_OAUTH_REDIRECT_BASE=https://llm.webplace.cc` (sem `/` final).  
   - Deve coincidir com o redirect registado no GCP (código: `app/dashboard/google_oauth.py` → `build_authorize_redirect_uri`).

4. **`DASHBOARD_ALLOWED_EMAILS`** — allowlist em minúsculas.

Erro típico: `redirect_uri_mismatch` → comparar URI no GCP com `DASHBOARD_OAUTH_REDIRECT_BASE` + `/dashboard/auth/google/callback`.

---

## WAF e limite de pedidos

No **painel da zona** Cloudflare (produtos disponíveis no plano): regras WAF, rate limiting, Bot Fight onde fizer sentido — sobretudo em paths de login e `POST` pesados.

---

## Parar Funnel e usar só o domínio na CF

1. Garantir túnel / proxy no domínio a apontar para a API local e **testar** HTTPS + dashboard.  
2. **Desligar Tailscale Funnel** no nó quando o novo caminho estiver OK — ver [Tailscale Funnel](https://tailscale.com/kb/1311/tailscale-funnel/) (`off` com os mesmos flags que usaste para ligar, ou `reset`; cuidado com **Serve** só-tailnet).  
3. Passos de túnel, tokens e menus: **`local-only/docs/CF_CLOUDFLARE_TACTICAL.md`**.

**Tailscale entre os teus PCs** mantém-se; mudas o **entrada pública** (Funnel vs domínio na CF).

---

## Resumo

1. TLS + OAuth: secções acima.  
2. Protecção na borda: WAF / rate limit no painel da zona.  
3. Túnel, Funnel off, credenciais: **`local-only/docs/CF_CLOUDFLARE_TACTICAL.md`**.
