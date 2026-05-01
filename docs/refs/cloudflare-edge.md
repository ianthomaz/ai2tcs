# Cloudflare em `llm.webplace.cc` (edge)

Contrato HTTP da API: [../02-api-integration.md](../02-api-integration.md). Topologia e decisões táticas (túnel, equipa CF, credenciais): **`local-only/docs/CF_CLOUDFLARE_TACTICAL.md`** no teu clone (gitignored).

---

## Nomenclatura

| Nome | O quê |
|------|--------|
| **Tailscale Funnel** | Expor serviço **Tailscale** à Internet pública. Caminho alternativo ao domínio na Cloudflare. |
| **Cloudflare Tunnel** (`cloudflared`) | Tráfego Internet → edge Cloudflare → túnel → processo `cloudflared` no teu lado → `127.0.0.1` / nginx. |

O DNS público (`llm.webplace.cc`) resolve na **edge Cloudflare** (registo **proxied**). Com **Cloudflare Tunnel**, o pedido segue para `cloudflared` no host onde corre a API (**llm_server**, ex. mini62) e daí para **`http://127.0.0.1:28471`**. Acesso **só na tailnet** (sem domínio público): [operacao-tailscale.md](./operacao-tailscale.md).

---

## TLS em `llm.webplace.cc` (browser → Google OAuth)

Checklist (ordem sugerida):

1. **Cloudflare (zona do domínio)**  
   - Registo `llm` (ou CNAME) **proxied** (nuvem laranja).  
   - **SSL/TLS** → modo **Full** ou **Full (strict)** conforme a origem tiver certificado válido ou não.  
   - **Always Use HTTPS** na zona, se aplicável.

2. **Google Cloud Console** (cliente OAuth **Aplicação Web**)  
   - **Origens JavaScript autorizadas:** exactamente o mesmo `scheme://host` que o browser usa (ex.: `https://llm.webplace.cc`). Para desenvolvimento local, acrescenta também `http://127.0.0.1:28471` se fores testar aí.  
   - **URIs de redireccionamento autorizados:** uma linha por origem, **exactamente**  
     `{DASHBOARD_OAUTH_REDIRECT_BASE}/dashboard/auth/google/callback`  
     (ex.: `https://llm.webplace.cc/dashboard/auth/google/callback`).

3. **`llm_api/.env`** (nunca versionar; ver [`llm_api/.env.example`](../../llm_api/.env.example))  
   - `DASHBOARD_GOOGLE_CLIENT_ID`, `DASHBOARD_GOOGLE_CLIENT_SECRET`  
   - `DASHBOARD_OAUTH_REDIRECT_BASE` = mesma origem que em (2), **sem barra final** (ex.: `https://llm.webplace.cc`).  
   - **`DASHBOARD_ALLOWED_EMAILS` obrigatório** se usares Google: lista separada por vírgulas, **e-mails em minúsculas**. Se ficar **vazio**, ninguém passa no login Google (o dashboard mostra mensagem a pedir configuração).

4. **Legado (opcional):** `DASHBOARD_USER` / `DASHBOARD_PASSWORD` — só se **não** tiveres os três campos OAuth preenchidos; ver [`02-api-integration.md`](../02-api-integration.md).

Erros típicos:

- **`redirect_uri_mismatch`** — comparar byte a byte o redirect no GCP com `DASHBOARD_OAUTH_REDIRECT_BASE` + `/dashboard/auth/google/callback`.  
- **“Allowlist vazia” / sem acesso** — preencher `DASHBOARD_ALLOWED_EMAILS` com pelo menos o teu e-mail Google (minúsculas).

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
