# Cloudflare em `llm.webplace.cc` (edge)

Contrato HTTP da API: [../02-api-integration.md](../02-api-integration.md). Topologia física: `local-only/` (gitignored).

---

## Nomenclatura

| Nome | O quê |
|------|--------|
| **Tailscale Funnel** | Produto **Tailscale** (expor serviço à Internet pela tailnet). **Não** confundir com Cloudflare. |
| **Cloudflare Tunnel** (`cloudflared`) | Tráfego **Internet → rede da Cloudflare → túnel → processo `cloudflared`** no teu lado; daí encaminhas para `127.0.0.1`/nginx/outro host. |
| **Cloudflare Zero Trust / Access** | Políticas na **Cloudflare** (login, lista de e-mails, WAF, rate limit) **antes** de chegar ao conector do túnel ou à origem. |

O DNS público (`llm.webplace.cc`) resolve na **edge Cloudflare**. O “quem manda pro **llm_server**” é o **conector do túnel** (ou nginx na origem), **não** o DNS por si só.

---

## TLS em `llm.webplace.cc` (browser → Google OAuth)

1. **Cloudflare (zona do domínio)**  
   - Registo `llm` (ou CNAME) **proxied** (nuvem laranja).  
   - **SSL/TLS** → modo **Full** ou **Full (strict)** conforme a origem (nginx/Linode) tiver certificado válido ou não. O visitante fala sempre **HTTPS** com a edge.  
   - **Always Use HTTPS** (redirect 301 http→https) activo na zona, se aplicável.

2. **Google Cloud Console** (mesmo cliente OAuth **Aplicação Web** que já usas)  
   - **APIs e serviços** → **Credenciais** → o **ID do cliente OAuth 2.0** usado em `DASHBOARD_GOOGLE_CLIENT_ID`.  
   - **Origens JavaScript autorizadas** — adicionar exactamente:  
     `https://llm.webplace.cc`  
   - **URIs de redireccionamento autorizados** — adicionar exactamente (um URI por linha, **sem** barra no fim do host):  
     `https://llm.webplace.cc/dashboard/auth/google/callback`  
   - Opcional (dev local): `http://127.0.0.1:28471` e `http://127.0.0.1:28471/dashboard/auth/google/callback` no mesmo cliente OAuth.

3. **`llm_api/.env` (produção pública)**  
   - `DASHBOARD_OAUTH_REDIRECT_BASE=https://llm.webplace.cc` (**sem** `/` final).  
   - A app monta o redirect canónico: `{DASHBOARD_OAUTH_REDIRECT_BASE}/dashboard/auth/google/callback` — tem de coincidir **exactamente** com o URI registado no GCP (código: `app/dashboard/google_oauth.py`, função `build_authorize_redirect_uri`).  
   - Abrir o dashboard no browser no **mesmo** origin: `https://llm.webplace.cc/dashboard` (e não misturar `www` / outro subdomínio sem o registar no GCP).

4. **`DASHBOARD_ALLOWED_EMAILS`**  
   - Lista em minúsculas no `.env`; quem não estiver na lista não entra após o Google.

Erro típico no login Google: `redirect_uri_mismatch` → comparar byte a byte o URI no GCP com o valor efectivo de `DASHBOARD_OAUTH_REDIRECT_BASE` + `/dashboard/auth/google/callback`.

---

## Zero Trust (Access)

**Não** liga sozinho ao túnel. É preciso criar **Application** em Zero Trust → **Access** → associar ao hostname (e opcionalmente ao path).

- Com política activa: o visitante passa pela **Cloudflare Access** (ex. Google Workspace / lista de e-mails) **antes** do pedido seguir para o túnel → origem.
- Sem política no hostname: o túnel encaminha **sem** essa camada Access (continuas a depender de auth na app, TLS, WAF, etc.).

### Dashboard (`/dashboard`)

A app já usa **Google OAuth** no dashboard. **Access à frente do mesmo hostname** pode impor **segundo** login (CF + app). Opções:

1. **Access só em paths** que não usem OAuth da app (raro), ou  
2. **Só Access** na entrada e simplificar login na app (mudança de produto), ou  
3. **Rate limit + WAF** na CF sem Access no `/dashboard`**, e Access só em rotas administrativas separadas (outro hostname), se existirem.

Decide por path/hostname; não misturar duas identidades Google sem testar o fluxo.

---

## Rate limit e WAF (recomendado já)

No dashboard **Cloudflare** (zona ou Zero Trust, conforme o produto):

- **Rate limiting** (ou **WAF custom rules**) no hostname da API: limite por IP, burst, paths críticos (`/dashboard/login`, `POST` pesados, etc.).
- **Bot Fight / Super Bot Fight Mode** (plano permitindo).
- **TLS**: Full (strict) com origem com certificado válido.

Isto **reduz martelada** antes de tocar no **llm_server**.

---

## Credenciais Cloudflare (onde estão; **não** commitar)

| O quê | Onde obter / guardar |
|--------|----------------------|
| Login na conta / zona | Dashboard Cloudflare + (para Zero Trust) equipa em **Zero Trust** no menu da CF. |
| **API Token** (automatizar DNS, etc.) | Perfil → **API Tokens** → criar com escopos mínimos. Guardar em gestor de secrets ou `local-only/`. |
| **Token do túnel** (`cloudflared`) | Zero Trust → **Networks** → **Tunnels** → criar/editar túnel → comando com `--token`. **Um segredo**; no **llm_server** usa env ou ficheiro fora do Git (ex. `systemd` `EnvironmentFile`). |
| **Zone ID / Account ID** | Overview da zona — úteis para API/Terraform; não vão para o repositório. |

Este repositório **não** armazena tokens Cloudflare.

---

## Migrar: parar **Tailscale Funnel** e expor só pela CF

Nome: é **Cloudflare Zero Trust** (equipa + túneis + Access). **“OneTrust”** é outro produto (cookies/consentimento).

1. **Zero Trust → Tunnels → Create tunnel** (ou usar túnel existente). Instalar `cloudflared` no **llm_server** (ou no host onde o túnel deve terminar) com o **token** do wizard.
2. **Public hostname** do túnel: `llm.webplace.cc` → serviço local da API (ex. `http://127.0.0.1:28471` se o TLS termina na CF; seguir a opção que o painel indicar para “no TLS verify” vs HTTPS local).
3. **Testar** `https://llm.webplace.cc/health` e login do dashboard **antes** de desligar o caminho antigo.
4. **Desligar Funnel** no nó Tailscale: ver [Tailscale Funnel](https://tailscale.com/kb/1311/tailscale-funnel/) e `tailscale funnel` na CLI da tua versão — em geral **`tailscale funnel reset`** limpa Funnel (confirmar se não afecta **Serve** que queiras manter só na tailnet; em dúvida, desliga Funnel pela **admin Tailscale** na máquina em vez de reset global).
5. **DNS** `llm` na zona `webplace.cc`: CNAME/proxy para o túnel, **proxied** (laranja), como já alinhas com TLS + OAuth na secção acima.
6. **Activar** rate limit / WAF na zona para esse hostname.

**Tailscale entre os teus PCs** continua independente; só estás a mudar **quem leva o tráfego público da Internet** até ao host (Funnel CF da Tailscale → **Tunnel + domínio** na Cloudflare).

---

## Resumo

1. **Tunnel CF** = caminho edge → origem; **não** substitui política Access.  
2. **Zero Trust Access** = activar **Application** + política no hostname/path desejado.  
3. **Funnel (Tailscale)** = outro produto; não assumir que “passa por Zero Trust” da CF.  
4. **Protecção imediata sem mudar código:** rate limit + WAF na CF neste hostname.  
5. **Migração Funnel → CF:** secção *Migrar* acima + credenciais só fora do Git.
