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

## Resumo

1. **Tunnel CF** = caminho edge → origem; **não** substitui política Access.  
2. **Zero Trust Access** = activar **Application** + política no hostname/path desejado.  
3. **Funnel (Tailscale)** = outro produto; não assumir que “passa por Zero Trust” da CF.  
4. **Protecção imediata sem mudar código:** rate limit + WAF na CF neste hostname.
