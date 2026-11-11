# 24 — Observação remota de operações (`GET /api/ops/observe`)

O olho remoto do agente na nuvem para inspecionar produção/stage sem SSH e sem conexão direta ao Postgres.
Segue o padrão canônico do ecossistema ITCS já adotado em `BikeAnjo_Sistema2026` e `0mmS_Tasks`.

| | |
|---|---|
| Rota | `GET /api/ops/observe` |
| Auth | Bearer `OPS_OBSERVE_TOKEN` (mínimo 32 caracteres) |
| Stealth | Token ausente, curto ou inválido devolve **HTTP 404 vazio** (`Cache-Control: no-store`) |
| Código | `llm_api/app/api/ops_observe.py`, `llm_api/app/ops/access.py`, `llm_api/app/ops/views.py`, `llm_api/app/ops/redact.py` |
| Testes | `llm_api/tests/test_ops_observe.py` |

---

## 1. Princípios e Limites de Segurança

1. **Estritamente Leitura:** Todas as visões SQL rodam sob `SET LOCAL transaction_read_only = on` com teto de execução `SET LOCAL statement_timeout = '5s'`.
2. **Zero SQL Livre:** Apenas visões estáticas catalogadas em `OPS_OBSERVE_VIEWS`. O cliente escolhe o nome da visão, nunca a query.
3. **Zero Dados Pessoais:**
   - Nenhuma coluna de pessoa (`user_id`, `email`, `phone`, `telefone`, `cpf`, `name`, `nome`, `birth_date`, perguntas ou respostas brutas de usuários) é selecionada.
   - Textos de logs e mensagens de erro passam obrigatoriamente por `redact_log_line`, que mascara tokens, Bearers, chaves `itcs_*`, `sk-*`, senhas, conexões Postgres, CPFs e telefones.
   - A guarda de testes automatizada (`test_ops_observe_views_no_personal_columns_in_select`) falha o build se qualquer `SELECT` futuro incluir colunas proibidas.
4. **Alerta de Acesso Negado:** Tentativas sem chave, com token curto ou inválido são registradas em log de segurança (`app.ops.observe`) com IP de origem antes de emitir o 404 silencioso.

---

## 2. Modos de Operação

Exatamente um dos parâmetros `source` ou `view` deve ser informado por chamada.

### Modo A: `source` (Cauda de Logs Limpos)

Lê as últimas $N$ linhas de logs da instância (`default: 200`, `max: 2000`), aplicando `redact_log_line`.

| `source` | Arquivo / Destino |
|---|---|
| `api` | `logs/api.log` |
| `worker` ou `jobs` | `logs/worker.log` |
| `pm2` | `$PM2_LOG_DIR/ai2tcs-out.log` |
| `pm2-err` | `$PM2_LOG_DIR/ai2tcs-error.log` |

Parâmetros adicionais para log:
- `lines`: Quantidade de linhas (1 a 2000).
- `grep`: Filtro case-insensitive de texto (máximo 100 caracteres).
- `since`: Timestamp ISO para descartar linhas anteriores.

Exemplo:
```bash
curl -H "Authorization: Bearer $OPS_OBSERVE_TOKEN" \
  "https://llm.webplace.cc/api/ops/observe?source=api&lines=50&grep=error"
```

### Modo B: `view` (Visões SQL Fixas de Negócio e Infra)

Permite ao agente inspecionar a saúde do cluster, filas, bancos e esquemas sem acesso direto ao banco.

| Visão (`view`) | O que devolve | Aceita `project_id`? | Aceita `days`? |
|---|---|---|---|
| `schema` | Tabelas públicas, colunas, tipos de dados e nulidade (auto-descoberta) | Não | Não |
| `migrations` | Últimas 30 migrações registradas em `_prisma_migrations` | Não | Não |
| `health` | Contagem de jobs pendentes (`queued`, `working`) e executados nas 24h | Não | Não |
| `jobs-queue` | Jobs em fila e em execução agrupados por projeto, modelo e status | Sim | Não |
| `jobs-summary` | Volume de jobs nas últimas 24h e 7 dias por projeto e status | Sim | Não |
| `errors` | Erros de jobs agrupados por mensagem sanitizada, modelo e projeto | Sim | Sim (1 a 30) |
| `llm-heavy` | Jobs que excederam limites de token ou chegaram perto do teto de contexto | Não | Não |
| `ratings` | Distribuição de avaliações shadow (`great`, `good`, `bad`, `stop`) | Sim | Não |
| `projects` | Catálogo de projetos ativos no Postgres com seus slugs e datas gerais | Sim | Não |
| `db-health` | Cache hit ratio do Postgres, conexões ativas por estado e queries longas | Não | Não |
| `db-tables` | Tamanho físico em disco das tabelas e índices (`pg_total_relation_size`) | Não | Não |

Exemplo de consulta:
```bash
# Ver jobs com falha nos últimos 7 dias no projeto bikeanjoall_2026:
curl -H "Authorization: Bearer $OPS_OBSERVE_TOKEN" \
  "https://llm.webplace.cc/api/ops/observe?view=errors&days=7&project_id=bikeanjoall_2026"
```

---

## 3. Respostas e Códigos HTTP

- **200 OK:** JSON com `view` ou `source`, payload sanitizado e `generated_at` em ISO UTC.
- **400 Bad Request:** Parâmetro inválido (ambos `source` e `view` passados, `days` fora de 1..30, visão desconhecida).
- **404 Not Found (Vazio):** Autenticação falhou ou token não configurado.
- **500 Internal Server Error:** Falha na leitura do log ou timeout de 5s no banco.

---

**Anterior:** [23-ecosystem-panorama.md](./23-ecosystem-panorama.md)
