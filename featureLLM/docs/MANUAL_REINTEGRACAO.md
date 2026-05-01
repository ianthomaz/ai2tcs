# Manual de Reintegração — Fleet LLM & Chaves por Projeto

Este documento orienta a migração para a nova arquitetura de autenticação, roteamento e gestão de modelos da API LLM (Abril 2026). Faz parte do repositório **ai2tcs** (`featureLLM/docs/`).

**Atenção:** o **`POST /router`** passou a responder com **JSON estruturado** (`action`, `confidence` numérico, `escalate_to`, etc.). O contrato antigo (três linhas / `confidence` string) deixou de ser o oficial — actualiza o orquestrador **na mesma janela em que actualizares a API**. Detalhe completo em [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md) § 3.2.

## 1. Nova Autenticação Dual

A partir de agora, a API suporta dois métodos de autenticação:

1.  **Token Global (Legado/Admin):** Continua funcionando via `Authorization: Bearer <LLM_API_TOKEN>`. Requer que `project_id` seja enviado no corpo da requisição.
2.  **Chave por Projeto (Novo/Recomendado):** Chaves no formato `itcs_<slug>_<hash>`. Quando usada, o `project_id` é inferido da chave. Se houver conflito entre a chave e o `project_id` no corpo, a API retornará 403.

### Como migrar um cliente:
1. Vá ao Dashboard em **Projetos > [Seu Projeto] > Chaves API**.
2. Gere uma nova chave e copie-a imediatamente.
3. No cliente, substitua o token global pela nova chave.

## 2. Fleet de Modelos (Aliases)

O sistema agora reconhece 4 aliases principais:

*   `fast` (llama3:8b): Triage, chat curto, classificações simples.
*   `compact` (qwen2.5:7b-instruct): Extração JSON, tarefas estruturadas.
*   `smart` (qwen2.5:14b-instruct): RAG profundo, respostas fundamentadas.
*   `reasoner` (deepseek-r1:8b): Lógica complexa, cálculos, cadeias de raciocínio.

Você pode forçar um modelo enviando `"model": "reasoner"` no corpo de requisições `/ask` ou `/router`.

## 3. Roteamento Triage-First (`/router`)

O endpoint `/router` agora utiliza um fluxo de triagem. O modelo `fast` avalia a mensagem e decide se:
*   **Responde na hora** (`action: "answer_now"`) para saudações ou perguntas triviais.
*   **Escala para um especialista** (`action: "escalate"`) com sugestão automática de modelo (`escalate_to`).

**Exemplo de resposta:**
```json
{
  "action": "escalate",
  "suggested_route": "ask",
  "escalate_to": "reasoner",
  "obs": "Usuário pediu explicação lógica sobre o processo.",
  "task_type": "reasoning",
  "confidence": 0.95
}
```

## 4. Ingest via Upload (`/ingest/upload`)

Agora você pode enviar arquivos diretamente via multipart/form-data:

```bash
curl -X POST -H "Authorization: Bearer <CHAVE>" \
     -F "file=@manual.pdf" \
     -F "project_id=meu-projeto" \
     http://localhost:28471/ingest/upload
```

## 5. Bibliotecas Partilhadas

Projetos podem agora referenciar conhecimentos comuns sem duplicar índices. Configure `shared_libraries: ["slug-comum"]` no `config_json` do seu projeto via Dashboard para que o `/ask` consulte automaticamente esses índices.

## 6. Revisão de viabilidade de deploy (sem subir ainda)

Use esta lista quando fores avaliar **quando** pôr a nova versão em produção. Não substitui testes na tua máquina.

### 6.1 Ordem segura (resumo)

1. **Parar** ou pôr em manutenção clientes que dependem do **contrato antigo** do `POST /router` (se houver).
2. **Correr migrações** PostgreSQL/Prisma (`prisma migrate deploy` no ambiente da API) — inclui `project_api_keys`, `shared_libraries`, coluna `Job.model_alias`.
3. **Subir** o binário/imagem novo da API **depois** das migrações (código que assume colunas/tabelas novas).
4. **Actualizar** orquestradores (ex. zapzap) para o **novo JSON** do `/router` na **mesma** janela, ou manter tráfego num host ainda na versão antiga até estarem alinhados.
5. **Opcional:** gerar chaves por projeto no Dashboard e migrar clientes do token global quando fizer sentido (o global continua válido).

### 6.2 Bloqueadores conhecidos

| Risco | Nota |
|-------|------|
| **Schema** | Sem migrações, a API nova pode falhar ao criar jobs ou validar chaves. |
| **`/router`** | Resposta mudou de formato; é o maior impacto em integrações antigas. |
| **RAM / Ollama** | Fleet com `reasoner` + vários workers (`LLM_WORKERS_JSON`) aumenta carga; validar no hardware real. |

### 6.3 Onde está o “prompt” do router

O **system prompt** de triagem (`ROUTER_SYSTEM` em `app/api/message_router.py`) é **só do servidor**. Instruções longas de negócio do WhatsApp devem continuar no **orquestrador cliente** ou na biblioteca do projeto (RAG), não misturar com o prompt de triagem em código sem necessidade — evita confusão e respostas fora do JSON esperado.

### 6.4 Manuais a cruzar com o código antes do go-live

| Documento | Foco da revisão |
|-----------|-----------------|
| [MANUAL_INTEGRACAO.md](./MANUAL_INTEGRACAO.md) | §2 auth, §3.2 `/router`, §3.8 `/edu`, ingest, troubleshooting. |
| [EDU_API_CONTRACT.md](./EDU_API_CONTRACT.md) | `model`, retry, fallback estruturado. |
| [OPERACAO_TAILSCALE.md](./OPERACAO_TAILSCALE.md) | Quem chama a API pela tailnet / proxy. |
| [DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md) | Migrações, workers por alias, variáveis `.env`. |
| [PROJECT_CONFIG_EXAMPLES.md](./PROJECT_CONFIG_EXAMPLES.md) | `shared_libraries`, `llm_options`, políticas RAG. |
