## PROMPT DE EXECUÇÃO (colar no Cursor do mini62 / anexar este MD)

Tu estás no repo **ai2tcs** no mini62. Objetivo: fechar o gap do §1.1 deste documento —
campos que o zap **já envia** e o serviço **ainda não injecta no prompt**.

### Escopo (fazer só isto neste run)

1. **`POST /router`** — `llm_api/app/api/message_router.py`
   - Declarar em `RouterRequest` (opcionais): `city`, `state`, `clearance`,
     `intended_clearance`, `interesse`, `journey_kind`, `journey_destination`,
     `next_event_name`, `next_event_at`.
   - Injectar em `user_parts` quando presentes (mesmo padrão dos campos atuais).
   - Manter `extra="ignore"` / campos desconhecidos sem erro (P1).
2. **`POST /ask`** — `llm_api/app/jobs/worker.py` → `_profile_from_request_context`
   - Promover para o perfil/metadata: `clearance`, `intended_clearance`,
     `journey_kind`, `journey_destination`, `next_event_name`, `next_event_at`,
     `current_time` (além do que já existe).
   - Confirmar que `app/rag/prompt.py` formata esses metadados no system/user
     prompt (ajustar formatação só se o dado entrar no dict e sumir no texto).
3. **Testes** — estender ou acrescentar cobertura em
   `llm_api/tests/test_api_zapzap_contract.py` (e unitário de montagem de prompt
   se já existir padrão no repo). Provar: campo no body → aparece no texto
   mandado ao modelo (ou no profile formatado), sem exigir Ollama live se os
   testes forem mockados.
4. **Commit local** com mensagem clara (só estes ficheiros). **Não push** a
   menos que o humano peça.

### Fora de escopo (NÃO fazer)

- Não alterar código do Bike Anjo / zapzap.
- Não reingerir, não seedar, não mexer em Chroma/DB, não tocar outros
  `project_id` (aiclaudia, estudosmobi, ian_zap, etc.).
- Não mudar `ROUTER_SYSTEM` global nem tom “friendly” neste run (tom BA =
  `extra_system_block` do project — run futuro).
- Não “melhorar a LLM”, temperatura, modelo, nem corpus.

### Consulta só-leitura (Bike Anjo) — pode abrir, não editar

Clone atualizado no mini62:

- Repo: `/Users/ianthomaz/Documents/projects/BikeAnjo_Sistema2026/`
- Contrato / payload: `zapzap/lib/llm-remote.js`, `zapzap/lib/router-user-context.js`
- Cópia canónica deste doc no BA: `docs/10d_ai2tcs_contrato_e_evolucao.md`
- Corpus / mapa (referência): `bibliotecaConteudoLLM/`, `mapaFluxosLLM/`
- Calibração: `docs/07b_ZAP_FLUXOS_E_LLM.md`

Se precisares confirmar o que o bot manda, lê esses ficheiros. **Zero writes**
fora de `ai2tcs/`.

### Critério de pronto

- Gap §1.1 fechado no código do serviço para os campos listados.
- Testes passando no que for razoável offline.
- Diff pequeno e revistável; resto do doc abaixo = spec detalhada.

### Mensagem curta do humano (VNC lento)

> Anexei o 10d. Executa só o **PROMPT DE EXECUÇÃO**. Não mexas no Bike Anjo.

---

# 10d. ai2tcs × Bike Anjo — contrato do bot e guia de evolução

O que o zapzap **envia** à LLM self-hosted (ai2tcs), o que **espera** de volta, e
**onde mexer** para cada tipo de problema. Escrito do lado do consumidor
(`zapzap/lib/llm-remote.js` é a fonte da verdade do que sai daqui); onde o lado
do serviço não é visível deste repo, a premissa está marcada como premissa.

Ciclo de calibração (julgar → exportar → mexer → reingerir → replay):
**[07b § julgamento](07b_ZAP_FLUXOS_E_LLM.md)** — não duplicado aqui.
Comportamento canônico da assistente: corpus
(`bibliotecaConteudoLLM/16_identidade_assistente.md` e `24_instrucoes_resposta.md`).

**Código do serviço (mini62):** `~/Documents/projects/ai2tcs/llm_api/`
— sobretudo `app/api/message_router.py` (`/router`) e
`app/jobs/worker.py` + `app/rag/prompt.py` (`/ask`).

---

## 1. Premissas (verificar do lado ai2tcs; se alguma for falsa, é lá que se ajusta)

| # | Premissa | Por que o bot depende dela |
|---|---|---|
| P1 | Campo desconhecido no body é **ignorado**, nunca erro | O bot adiciona campos de contexto sem versionar o contrato; validação estrita quebraria o roteador a cada evolução |
| P1b | **Ignorado ≠ usado.** Campo extra no HTTP pode ser aceito e **nunca chegar ao prompt** | Ver [§1.1](#11-enviar--chegar-ao-prompt--gap-jul2026). Calibrar como se o modelo “visse” a cidade/jornada sem checar o código do ai2tcs é perda de tempo |
| P2 | `/router` responde síncrono (~15s); `/ask` é **job** (`job_id` → `/status/{id}` → `/result/{id}`) | Timeouts e polling do cliente estão calibrados para isso |
| P3 | O modelo **não guarda estado** entre chamadas | Todo contexto vai em cada request; nada pode depender de "lembrar" |
| P4 | RAG do `project_id: bikeanjoall_2026` = `bibliotecaConteudoLLM` + `mapaFluxosLLM` ([10a](10a_llm_ingest_bikeanjo.md)) | Mexeu no corpus sem reingerir = nada mudou |
| P5 | `confidence` do `/router` vem como **número 0–1** | É o que alimenta as bandas (0.75/0.45), o filtro da avaliação e a tabela confiança×nota. String ou omissão degrada para "média" e mistura "médio" com "não sei". No ai2tcs, `_coerce_confidence` ainda aceita legado `high/medium/low` |
| P6 | `no_answer` é resultado **válido e bem-vindo** do `/ask` | O canal prefere silêncio a invenção; o bot trata `no_answer` como "não responder" |

### 1.1 Enviar ≠ chegar ao prompt — gap (jul/2026)

Estado observado no código do ai2tcs no mini62. O zap **já manda** o contexto
rico; o serviço **não o injecta** no prompt (ainda).

| Endpoint | O que o zap manda | O que o ai2tcs mete no prompt da LLM |
|---|---|---|
| `POST /router` | `city`, `state`, `clearance`, `intended_clearance`, `interesse`, `journey_kind`, `journey_destination`, `next_event_name`, `next_event_at` (+ flags e `last_messages`) | Só campos **declarados** em `RouterRequest` e montados em `user_parts`: `user_name`, flags de cadastro/onboarding, `current_flow`/`current_step`, `last_messages` + chunks RAG. O resto cai em `extra="ignore"` (P1) e **não aparece** no texto do user |
| `POST /ask` | whitelist em `_ask` inclui clearance, journey_*, next_event_*, `current_time`, … | `_profile_from_request_context` só promove para o perfil: `name`, `birth_date`, e metadata `cep`/`city`/`state`/`health`/`interesse`/`registered`. **Clearance, jornada, próximo evento e `current_time` são gravados no job e descartados na hora de montar o prompt** |

Consequência: o mapa
[mapaFluxosLLM/10](../mapaFluxosLLM/10_mapa_roteador_public_router_2026.md)
descreve o **uso esperado** dos campos. Enquanto o gap existir, esse uso é
spec — não comportamento. Sintoma “ignora cidade / jornada” **não** se resolve
só mexendo no corpus nem só no tom do system prompt.

**Ordem correcta ao evoluir um campo de contexto:**

1. Zap monta o valor (`router-user-context.js` / flows).
2. Zap **whitelist** (`askRouter` body **e** `_ask` user_context — são duas).
3. ai2tcs **declara e injecta**:
   - `/router` → campo em `RouterRequest` + linha em `user_parts` (`message_router.py`);
   - `/ask` → chave em `_profile_from_request_context` (`worker.py`) — e, se
     precisar de regra de uso, texto no corpus ou `extra_system_block` do project.
4. Só então: reingerir (se mexeu no corpus) → replay shadow.

Sem o passo 3, o campo “viaja” no JSON e a LLM nunca o vê.

### 1.2 `clearance` não entra no prompt — decisão, não esquecimento

O gap do §1.1 foi fechado, **menos** para `clearance` / `intended_clearance`.
Esses dois continuam aceitos no body e gravados no job, mas **não** são montados
em `user_parts` nem promovidos em `_profile_from_request_context`.

Razão: NOIA (New / Outside / Inside / Adm) é **autorização**, não contexto de
conversa. A clearance já foi validada antes da chamada, e os fluxos em que I/A
executam algo (nota fiscal, pedido de pagamento) rodam com texto pré-definido,
sem consultar a LLM semanticamente — quando ela entra, entra depois da validação
e só para entregar. Expor um nível de permissão no prompt só convida o modelo a
raciocinar sobre acesso, que é exactamente o que o [§5](#5-autoridade--o-que-a-llm-nunca-decide)
proíbe. O sinal com sentido para a conversa é a **situação na jornada**
(`journey_kind` / `journey_destination`), e esse sim é injectado.

Quem quiser reverter: os dois campos estão declarados e comentados nos dois
lados (`message_router.py` e `worker.py`), com o motivo escrito ao lado.

---

## 2. Contrato `POST /router`

Código: `ai2tcs/llm_api/app/api/message_router.py` (`ROUTER_SYSTEM` + montagem
`user_parts`).

### O bot envia

| Campo | Tipo | Conteúdo | Chega ao prompt hoje? |
|---|---|---|---|
| `message` | string | Inbound (rajadas já consolidadas numa string) | sim |
| `project_id` | string | `bikeanjoall_2026` | sim (RAG + config) |
| `user_name` | string? | Primeiro nome | sim |
| `current_flow` / `current_step` | string? | Fluxo estruturado ativo, se houver | sim |
| `user_registered` / `onboarding_active` / `onboarding_completed` | bool | Flags históricas | sim |
| `city`, `state` | string? | Do cadastro | sim (§1.1 fechado) |
| `clearance`, `intended_clearance` | string? | Nível N/O/I/A e trilha pretendida | **não — por decisão** ([§1.2](#12-clearance-não-entra-no-prompt--decisão-não-esquecimento)) |
| `interesse` | string? | Interesse anotado no contato | sim |
| `journey_kind`, `journey_destination` | string? | **Jornada POfR aberta** e destino (`/eixo/event-…`) | sim |
| `next_event_name`, `next_event_at` | string? | Próximo evento inscrito (ISO) | sim |
| `last_messages` | string[] | Até 5, prefixadas `user:` / `assistant:` | sim |

Origem do contexto rico: `zapzap/lib/router-user-context.js`. Uso esperado de
cada campo (quando o gap fechar): [mapaFluxosLLM/10](../mapaFluxosLLM/10_mapa_roteador_public_router_2026.md)
(está no corpus de propósito — o modelo lê via RAG). **Campo ausente = plataforma não
sabe; nunca inventar.**

### O bot espera

| Campo API | Contrato |
|---|---|
| `suggested_route` | rota canónica (`ask`, `cadastro`, `saudacao`, `escalar_humano`, `documento`, `status`, `agradecimento`, `cursor`); ausente → bot assume `ask`. Lista viva = `ZAPZAP_ROUTES` no ai2tcs |
| `action` | `answer_now` **ou** `escalate` (não “seguir para ask” — escalate é o default quando não há resposta pronta; o bot decide o próximo passo) |
| `answer` | Só com `answer_now`, e **já no formato WhatsApp** (curto, link-first, sem markdown) |
| `confidence` | **Número 0–1** (P5) — a régua de corte é do bot, o número é do serviço |
| `obs` | Nota curta no JSON do serviço. O zap mapeia `obs` → `reason` nos logs de julgamento — escrever para humano ler |
| `escalate_to` / `task_type` | Opcionais; o serviço pode escolher `compact`/`smart`/`reasoner` via `selection.py` |

### Regra de ouro do `answer_now`

`answer_now` é a LLM afirmando "esta resposta está pronta para um contato real".
Só usar quando cumpre o corpus (`24_instrucoes`): 1 frase + link, zero pedido de
dado que o site coleta, zero invenção. Na dúvida → `escalate` / rota `ask` ou
confiança baixa. **A confiança do `answer_now` descreve a resposta; nos demais
casos descreve só a decisão de rotear** — o bot grava `answer_source` para não
confundir as duas na avaliação.

> ⚠️ O `ROUTER_SYSTEM` default no ai2tcs pede resposta "friendly Portuguese".
> O corpus Bike Anjo (`16`/`24`) manda o contrário: pragmática, sem conversinha.
> Enquanto o default genérico vencer, `answer_now` tende a tom errado mesmo com
> RAG bom. Ajuste preferível no ai2tcs: `config_json.router.extra_system_block`
> do project `bikeanjoall_2026` (ou endurecer `ROUTER_SYSTEM` só para este
> project) — **não** inventar tom no zap.

---

## 3. Contrato `POST /ask`

Código: `ai2tcs/llm_api/app/api/ask.py` (job) → `app/jobs/worker.py`
(`_profile_from_request_context`) → `app/rag/prompt.py` (`build_system_prompt`).

### O bot envia

`question`, `history` (últimas trocas), `system_prompt` (o do runtime — o mesmo
que o replay usa) e `user_context`:

| Grupo | Campos | No prompt hoje? |
|---|---|---|
| Identidade | `name`, `birth_date`, `registered` (bool) | sim (nome/idade; `registered` em metadata) |
| Local | `cep`, `city`, `state` | sim (metadata) |
| Saúde | `health` | sim (metadata) |
| Momento | `current_time` (America/Sao_Paulo), `interesse` | sim (metadata) |
| Plataforma | `journey_kind`, `journey_destination`, `next_event_name`, `next_event_at` | sim (metadata) |
| Autorização | `clearance`, `intended_clearance` | **não — por decisão** ([§1.2](#12-clearance-não-entra-no-prompt--decisão-não-esquecimento)) |

> ⚠️ Histórico (jul/2026): a whitelist do **cliente** descartava em silêncio tudo
> além dos 6 primeiros campos — `current_time`, `interesse` e `registered` eram
> montados e **nunca chegavam**. Corrigido no zap; lição no próprio código:
> campo de contexto novo **tem** de entrar na whitelist de `_ask`, senão morre
> calado.
>
> Segunda lição (mesmo mês, lado ai2tcs): passar na whitelist do cliente **não
> basta** — o worker ainda tem de listar a chave em
> `_profile_from_request_context`. Senão o job guarda o JSON e o prompt sai
> sem o dado.

### O bot espera

- `answer` **final, já no formato do canal**: curto, link-first, URL crua em
  linha própria (o cliente sanitiza markdown por segurança, mas o certo é nem
  emitir), sem preâmbulo, sem "posso ajudar em mais algo?".
- `no_answer` quando não há resposta honesta (P6). Silêncio > invenção, sempre.
- O contexto é para **especificidade**, não para exibição: usar a cidade para
  escolher o EBA, não para dizer "vejo que você mora em X".

---

## 4. Onde mexer, por sintoma

| Sintoma observado no julgamento | Onde mexer | Como |
|---|---|---|
| Conteúdo errado ou desatualizado | **Corpus** (`bibliotecaConteudoLLM/`) | Corrigir o doc → reingerir ([10a](10a_llm_ingest_bikeanjo.md)) → replay |
| Fato certo, tom errado (conversinha, longo, caloroso) | Corpus `16` + `24`; se persistir, `extra_system_block` / system prompt no ai2tcs | O 16 já define: pragmática, objetiva, sem manutenção de conversa. Atenção ao default "friendly" do `ROUTER_SYSTEM` (§2) |
| Rota errada (ex.: cadastro para quem pedia evento) | **Lado ai2tcs** do `/router` + [mapaFluxosLLM/10](../mapaFluxosLLM/10_mapa_roteador_public_router_2026.md) | O mapa 10 é a spec do roteador e está no corpus. Heurísticas genéricas estão em `ROUTER_SYSTEM` |
| Ignora contexto (cidade/jornada presentes no shadow, resposta genérica) | **Primeiro §1.1** — injectar no ai2tcs; só depois prompt/corpus | Se o campo não está em `user_parts` / `_profile_from_request_context`, mexer em prompt é teatro |
| Falta contexto que a plataforma tem | **Lado de cá**: `router-user-context.js` + whitelists (`askRouter` e `_ask`) **e** inject no ai2tcs (§1.1 passo 3) | Lembrar: são **duas** whitelists no zap + **um** mapeamento no serviço |
| Confiança não separa bom de ruim | **Lado ai2tcs** (como o número é gerado) | A tabela confiança×nota em `/adm/shadow-llm` é o veredicto; `confidence_value` cru está gravado para recalibrar corte |
| Inventou ação/link/evento | Corpus `24` (proibições) + prompt ai2tcs | Invenção é 👎 automático com motivo; se reincidir após reingest, é prompt |

---

## 5. Autoridade — o que a LLM nunca decide

- **Não executa nada.** Não cria POfR, não mexe em cadastro, não gera magic link
  "por conta". O único caminho aceitável, quando amadurecer: **propor JSON →
  backend valida contra whitelist → backend executa** — mesmo contrato do
  frontend ([02b §3](02b_POFR.md)). Ser self-hosted muda quem *vê* o dado, não
  quem tem *autoridade* sobre ele.
- **Não promete** ("vou unificar suas contas", "já atualizei") — prometer é
  executar com palavras.
- Precedente pronto no código: extração de NF já usa o padrão "responda SÓ um
  JSON com estas chaves permitidas" (`buildPaymentNfJsonExtractQuestion` em
  `llm-remote.js`). Qualquer saída estruturada nova segue esse molde.

## 6. "Está atendendo bem" — como saber sem achismo

1. **Taxa de 👎 caindo** entre rodadas de calibração (export JSONL data a data).
2. **👍👍 estáveis no replay** — `tools/shadow-eval.js --rating=great` sem
   mudanças inesperadas após mexer no corpus.
3. **Confiança separando**: 👎 concentrados na banda baixa na tabela
   confiança×nota. Enquanto não separar, confiança não serve de filtro.
4. **Zero invenções** — uma já é falha de contrato, não "caso infeliz".
5. Só com 1–4 sustentados é que se discute sair do shadow (Live_AGENT).

## 7. Checklist rápido antes de “melhorar a LLM”

Antes de pedir mudança de modelo, temperatura ou prompt longo:

1. O campo que a resposta deveria usar **aparece no JSON** do shadow / log do zap?
2. Esse campo **entra no prompt** no ai2tcs (§1.1)? Se não → código do serviço, não corpus.
3. Corpus reingerido depois da última edição de doc ([10a](10a_llm_ingest_bikeanjo.md))?
4. Replay dos 👍👍 ainda passa (`shadow-eval`)?
5. Só então: `extra_system_block` / corpus `16`+`24` / calibração de confiança.
