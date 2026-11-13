# Agentes no mini62 · uso seguro para treinar a LLM

Complemento operacional de [segunda-opiniao-agente.md](./segunda-opiniao-agente.md).
Fase atual: **só consulta**. Sem Meta, sem liberar vaga, sem bridge de chat.

## O que existe na máquina (inventário 12/nov/2026)

| Peça | Onde |
|---|---|
| ai2tcs API | este repo, tipicamente `:28471` |
| Cursor.app + CLI | `/Applications/Cursor.app` · `…/bin/cursor` |
| Cursor Agent | `~/.local/bin/agent` → `cursor-agent` |
| Antigravity.app | instalado; fluxo humano BA em `BikeAnjo_Sistema2026/antigravity/ida` ↔ `retornos` |
| zapCursorAgent | outro repo, bridge GChat `:28472` · **fora** deste desenho |

## Cursor (caminho da fila automática)

1. One-shot por caso: `second_opinion_worker.py` grava o prompt em `caso.md` numa pasta temporária
   vazia e chama o agente nela → JSON validado pela API. Comando, perfil restrito e o que perguntar
   ao próprio Cursor: [cursor-cli-perguntas.md](./cursor-cli-perguntas.md).
2. Sem sessão de chat, sem `:28472`, sem WhatsApp.
3. Clone **só leitura** + usuário OS sem deploy/Meta/escrita no repo de trabalho.
4. Modo ask / sem auto-run (ou allowlist mínima de leitura); timeout; kill.
5. **Keychain:** o Agent precisa do keychain desbloqueado na sessão do Mac. SSH frio
   sozinho falha. O caller é launchd/processo **já logado** no mini62, não
   `security unlock-keychain` remoto.
6. Teto diário (ex. 20) + kill switch na fila + log (`source_ref`, duração, ok/fail).

## Antigravity

| Modo | Quando |
|---|---|
| Ida/retorno (humano) | Auditar desenho, rotular lote, comparar com Cursor |
| CLI headless | Só se existir estável; mesmo contrato do `second-opinion.sh` |

Sem CLI confiável: **não** entra na fila automática da fase 1.

## Gemini (API)

Fallback **futuro** da LLM local em casos sem urgência (plano/chave do dono). Não é o
professor principal nem substitui `/ratings` + exemplos. Abrir só com decisão explícita.

## zapCursorAgent · proibido neste fio

Bridge GChat → Cursor com sessão contínua. Porta larga. Segunda opinião do shadow é o
**oposto**: pacote fechado, um JSON, sem canal.

## Observe genérico vs fato do caso

`GET /api/ops/observe` ([24](../24-ops-observe.md)) não devolve «esta pessoa liberou a
vaga». Na fase 1 o Zap/sistemaBA coloca no pacote `slot_status`,
`button_already_used`, `identity_ok_for_slot`. O estado de agora vem da porta estreita do
projeto, que o **worker** chama com a chave só leitura ([26 § 7](../26-second-opinion.md#7-consulta-só-leitura-ao-sistema-do-projeto));
o agente não consulta nada e nunca roda SQL livre.

## Horizonte

- Fase 5 de **ação**: no começo Cursor no mini62 (porta por ação); depois middleware.
- Mais tarde: MCP / portas internas (evento, conversa associação, e-mail) com o mesmo
  rigor de identidade e lista fechada. Sem pressa de tirar o Cursor no médio prazo.
