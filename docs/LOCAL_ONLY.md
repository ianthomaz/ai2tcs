# Pasta `local-only/` (não versionada)

Cria uma pasta **`local-only/`** na **raiz do clone** (ao lado de `README.md`). Ela está listada no [`.gitignore`](../.gitignore) e **nunca** deve ser commitada.

## Para que serve

- Mapa da **tua** rede: IPs Tailscale atuais, hostnames reais, URLs públicas de produção.
- Notas de **proxy / túneis** (comandos com endereços reais).
- Cópias de snippets de nginx, variáveis sensíveis, lembretes de operações.

## O que fica no repositório público

- Contratos HTTP, exemplos com **placeholders** (`<tailnet-host>`, `<public-llm-host>`).
- [`featureLLM/.env.example`](../featureLLM/.env.example) com nomes de variáveis, sem segredos.

Assim podes manter o repo público legível para humanos e para IAs, sem expor a topologia real.
