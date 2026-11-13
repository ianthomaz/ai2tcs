# Cursor CLI no mini62: o que já se sabe e o que perguntar ao próprio Cursor

O professor da segunda opinião ([26](../26-second-opinion.md)) é o Cursor Agent rodando sem
tela, num perfil **mais estreito** que o Cursor de uso diário da mesma máquina. Este documento
junta o que a documentação oficial garante (cursor.com/docs/cli, lida em 13/nov/2026) e o
roteiro de perguntas para o próprio Cursor responder no mini62, antes do primeiro caso real.

## 1. O que a documentação garante

| Tema | O que vale |
|---|---|
| Sem tela | `agent -p` (`--print`) roda um prompt e sai; `--output-format text` imprime só a resposta final (`json` e `stream-json` também existem) |
| Só leitura | `--mode ask`: explora e responde, sem editar; `--mode plan` planeja |
| Pasta | `--workspace <pasta>` fixa a raiz; `--trust` aceita a pasta sem pergunta (só sem tela) |
| Permissões | `permissions.allow` / `permissions.deny` com `Shell(cmd)`, `Read(glob)`, `Write(glob)`, `WebFetch(domínio)`, `Mcp(servidor:ferramenta)`; **deny vence allow**, e `--force` não passa por cima de deny |
| Onde ficam | global em `~/.cursor/cli-config.json`; por projeto em `<pasta>/.cursor/cli.json` (só permissões) |
| Perfil paralelo | `CURSOR_CONFIG_DIR` troca a pasta de configuração inteira: um segundo perfil na mesma máquina, sem tocar no de uso diário |
| Sandbox | `--sandbox enabled`; na configuração, `sandbox.mode`, `sandbox.networkAccess` e `sandbox.readBoundary` (`system` ou `workspace`) |
| Aprovação | `approvalMode`: `allowlist` · `auto-review` · `unrestricted` |
| Login de automação | `CURSOR_API_KEY` (ou `--api-key`); `agent status` / `agent whoami` conferem |
| MCP | lê `.cursor/mcp.json` e `~/.cursor/mcp.json`; `agent mcp disable <id>` desliga um |
| Modelo | `agent models` lista; `--model` escolhe |
| Cuidado | em modo `-p` o agente **pode escrever arquivos na pasta** mesmo sem `--force`; por isso a pasta é temporária e vazia |

O que a documentação **não** diz: prompt pela entrada padrão; uma opção que desliga todas as
ferramentas de uma vez; rodar como outro usuário do macOS; se `CURSOR_API_KEY` dispensa o
keychain desbloqueado.

## 2. Perfil restrito proposto

Pasta `~/.cursor-professor/`, apontada por `CURSOR_CONFIG_DIR` só no worker. Chave de API
própria (`CURSOR_API_KEY` do professor), separada da sessão de uso diário.

`~/.cursor-professor/cli-config.json`:

```json
{
  "version": 1,
  "approvalMode": "allowlist",
  "sandbox": { "mode": "enabled", "networkAccess": false, "readBoundary": "workspace" },
  "permissions": {
    "allow": ["Read(caso.md)"],
    "deny": ["Shell(*)", "Write(**)", "WebFetch(*)", "Mcp(*:*)"]
  }
}
```

Comando no worker (`SECOND_OPINION_AGENT_CMD`):

```bash
agent -p --mode ask --output-format text --trust --sandbox enabled \
  --workspace {workdir} "Leia {prompt_file} e responda só com o JSON pedido nele."
```

O formato exato das chaves de `sandbox` e o comportamento combinado com `-p` são inferência
da documentação: confere-se no mini62 (seção 3 e 4).

## 3. Perguntas para o próprio Cursor

Abrir o Cursor no mini62, no perfil de uso diário, e colar uma pergunta por vez. Guardar a
resposta embaixo de cada uma neste documento.

1. «Em `agent -p --mode ask`, o agente ainda pode rodar comando de shell ou escrever arquivo?
   Se pode, qual configuração bloqueia os dois de vez?»
2. «Com `CURSOR_CONFIG_DIR=~/.cursor-professor`, o agente lê só esse `cli-config.json`, ou
   também `~/.cursor/cli-config.json` e `~/.cursor/mcp.json`? Como garantir que nenhum MCP
   do perfil diário carregue?»
3. «O `cli-config.json` da seção 2 é válido? `sandbox.networkAccess: false` e
   `readBoundary: workspace` valem em modo `-p`?»
4. «`CURSOR_API_KEY` sozinha autentica num processo do launchd, sem keychain desbloqueado e
   sem `agent login`?»
5. «Dá para rodar o `agent` como outro usuário do macOS (sem acesso à minha pasta de
   projetos), e o que esse usuário precisa ter instalado?»
6. «O `agent -p` aceita o prompt pela entrada padrão?» (se sim, o worker pode dispensar o
   arquivo `caso.md`)
7. «Qual modelo usar para responder um JSON curto com o menor custo, e como fixar no
   comando?»

## 4. Prova no mini62 (depois das respostas)

1. Criar `~/.cursor-professor/` com o `cli-config.json` da seção 2 (ajustado pelas respostas).
2. `CURSOR_CONFIG_DIR=~/.cursor-professor agent status` → mostra a conta do professor.
3. `second_opinion_worker.py --dry-run` com o comando da seção 2 → imprime um JSON.
4. Prova negativa, numa pasta temporária: pedir ao agente «crie o arquivo x.txt» e «rode `ls ~`»
   → nada criado, nada listado fora da pasta.

Só depois disso o worker entra em `--listen`.
