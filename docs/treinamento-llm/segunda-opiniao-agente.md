# Segunda opinião por agente (Cursor / Antigravity no mini62)

**Canônico neste repositório** (`docs/treinamento-llm/`). Estado: proposta do dono
(12/nov/2026), sem código de fila ainda.

- Índice da pasta: [README.md](./README.md)
- Higiene do eval `/ask`: [higiene-eval-ask.md](./higiene-eval-ask.md)
- Operação segura dos agentes: [agentes-seguros-mini62.md](./agentes-seguros-mini62.md)
- Lado Zap (Bike Anjo): monorepo `docs/07b_ZAP_FLUXOS_E_LLM.md` § shadow avançado
- Stub no BA: `docs/contracts/ai2tcs/SEGUNDA_OPINIAO_AGENTE.md` → aponta para cá

## O objetivo é treinar a LLM local, não substituí-la

A LLM do ai2tcs responde hoje «meio burra» em casos simples. O agente maior (Cursor ou
Antigravity no mini62) entra como **professor**: nota a hipótese local, diz o caminho
certo e reformula. O par vira exemplo. A medida de sucesso é a LLM local **precisar cada
vez menos** da segunda opinião nos mesmos tipos de pergunta.

**Não é aprovação de envio.** A segunda opinião não manda Zap nem autoriza mandar. No
começo **também não executa ação**: só consulta o estado do caso e propõe texto (e, se
couber, `suggested_action` para humano ou para fases futuras).

Gemini / API de mercado **não** é o caminho preferido de treino (cria dependência). Pode
entrar depois como **fallback** da LLM local em casos sem urgência (plano Gemini do dono);
isso é outra frente, não este desenho. Urgência de tirar o Cursor do processo de ação no
médio prazo: **não há**. Quando houver execução automática, o começo é via Cursor no
mini62; mais tarde a mesma ação migra para middleware no servidor (e, no horizonte,
portas MCP para quem é interno: abrir evento, conversar sobre a associação, e-mail).

## Caso exemplo (canônico · confirmação de presença + liberar vaga)

Caso real usado para fechar o desenho (12/nov/2026). Nomes de conta e copy como
ocorreram; telefone não precisa viajar no pacote do agente.

**Contexto.** Campanha de confirmação de um evento no Rio: mensagem com botões
(confirmar / não confirmar · liberar vaga).

**Texto da pessoa (depois da campanha):**

> Bom dia ! Vou precisar libertar a vaga . Larissa não vai conseguir comparecer 😢

**Hipótese do shadow (errada):** algo na linha de «há registro de interesse na EBA Lagoa;
ainda não confirmamos a inscrição; aguarde».

**O que aconteceu em seguida na produção.** A conta (AAJA9) **já liberou a vaga pelo
botão**. Duas evidências da mesma intenção: prosa inequívoca + clique no botão.

### O que o caso ensina (genérico)

| Momento | Sem olhar o estado da inscrição | Com consulta só leitura ao estado do caso |
|---|---|---|
| Resposta imediata (sem janela) | Caminho barato e seguro: pedir para usar os **botões** da mensagem de confirmação / liberação | Ainda não sabe se o botão já foi usado |
| Depois de uma **janela de tempo** (ex. ~2 min) e a pessoa **já clicou** | Continua às cegas (risco de pedir botão de novo ou «liberar» outra vez) | «Fique tranquila, sua vaga já está liberada.» Sem reexecutar. Tom humano. |
| Depois da janela e **ainda não clicou** | Idem: orientar o botão | Orientar o botão; gravar `suggested_action: release_slot` para aprendizado; **não** executar (fase só consulta) |
| Só pacote sem estado | Já dá para marcar a hipótese local como caminho errado (consulta × ação) | O estado transforma «corrigir a intenção» em «responder ao fato» |

**Mínimo útil sem nenhuma ação automática:** estrutura segura que **consulta** a situação
da pessoa **naquela** ocorrência / campanha (inscrita, confirmada, vaga liberada, botão
já consumido) e escolhe entre duas respostas-tipo:

1. já liberou → confirmar com calma («sua vaga já está liberada»);
2. ainda não → «use o botão correspondente para liberar ou confirmar a vaga».

Isso já treina a LLM e já seria simpático no caso AAJA9. Executar a liberação sem clique
humano é fase posterior (abaixo).

### Janela de tempo

A pessoa pode mandar várias mensagens e/ou apertar o botão logo depois do texto. Processar
só a primeira frase na hora gera resposta dúbia. A orquestração deste **tipo** de caso
(resposta a campanha de confirmação + texto que cheira a liberar/confirmar) deve:

1. reconhecer a classe barata («campanha ativa → botões»);
2. **esperar** uma janela curta (valor exato a definir; ordem de minutos);
3. juntar o que chegou na janela + o estado do caso;
4. só então pedir segunda opinião / montar a alternativa proposta.

A janela de 24 h do WhatsApp (atendimento) é outra coisa: aqui a janela é **debounce de
contexto** antes de julgar ou sugerir.

## Premissas (dono)

1. **Volume pequeno:** até **20 consultas por dia** no total (Cursor + Antigravity).
2. **Só leitura no começo** (fases 0–3). O agente consulta e opina; não manda mensagem;
   não libera vaga.
3. **Crédito que o dono já tem** no Cursor e no Antigravity no mini62. Claude fora deste
   fio. Gemini API: fallback futuro da LLM, não professor principal.
4. **Triangulação:** hipótese local · opinião do agente · o que a pessoa (ou o botão) de
   fato fez.
5. Muita resposta sai só do pacote + docs; **este tipo de caso exige fato de inscrição**
   no pacote (montado pelo Zap/sistemaBA), não inventado pelo agente.

## Caminho construtivo (fases)

| Fase | O que acontece | Quem age |
|---|---|---|
| 0 | Prova no mini62: pacotes falsos + 1 caso tipo AAJA9 em **só leitura**; JSON válido | dono autoriza o ensaio |
| 1 | Depois da janela: consulta estado → alternativa «já liberada» **ou** «use o botão»; nota da hipótese local | ninguém executa ação |
| 2 | Painel: hipótese local × alternativa do professor; `suggested_action` visível | quem atende pode aplicar / responder |
| 3 | Exemplos vão a `/ratings` e ao RAG; mede queda de erros do mesmo tipo | — |
| 4 | Agente **confirma** que a ação cabe (mesma conta, mesma vaga, lista fechada); painel com um clique | pessoa |
| 5 | Ação sem clique: **no começo via Cursor no mini62** (porta estreita por ação); depois a mesma ação no **middleware** do servidor (LLM só sugere) | agente → depois servidor |
| ∞ | Horizonte: MCP / portas internas (abrir evento, falar da associação, e-mail) reutilizam o mesmo rigor de identidade e lista fechada | interno |

Não há pressa de tirar o Cursor da fase 5. Middleware e MCP vêm quando o contrato de
ação (tipo, prova de identidade, registro, kill switch) já estiver sólido no mini62.

## Fluxo (fase só consulta)

```
mensagem (campanha / ação?) ──▶ janela curta ──▶ Zap monta pacote + fatos do caso
        │                                              │
        │                                              ▼
        │                                    ai2tcs fila (teto 20/dia)
        │                                              │
        │                         Cursor ou Antigravity (mini62, só leitura)
        │                                              │
        ▼                                              ▼
   shadow hipótese local ◀──── alternativa + nota + suggested_action (sem executar)
```

1. Shadow grava a hipótese como hoje.
2. Se a classe do caso pede janela, a segunda opinião **espera** o fim da janela.
3. Zap/sistemaBA coloca no pacote os **fatos já resolvidos** (abaixo). O agente não
   precisa de telefone cru.
4. Worker `second_opinion_worker.py` no mini62 acorda sob demanda via campainha local, chamando Cursor one-shot.
5. JSON volta ao caso; `/ratings` quando houver nota humana ou do professor.

**Não** usar o bridge `zapCursorAgent` (:28472 / GChat). É o oposto: sessão aberta,
canal de chat. Aqui: um processo, um pacote, um JSON, sem Meta.

## O pacote (mínimo para o caso exemplo)

Além do que o shadow já monta (texto, hipótese, sinais, catálogo de ações, paths de doc):

| Campo (ideia) | Para quê |
|---|---|
| `campaign_kind` | ex. confirmação de presença |
| `buttons_offered` | confirmar / liberar (rótulos seguros) |
| `slot_status` | ex. `registered` · `confirmed` · `released` · `unknown` |
| `button_already_used` | se o clique de liberar/confirmar já foi registrado |
| `identity_ok_for_slot` | boolean: a conta desta conversa pode mexer nesta vaga (o Zap calcula; o agente **não** decide identidade no escuro) |
| `source_ref` | `zap:log:…` |

**Não entra no pacote enviado ao modelo de mercado:** telefone, nome completo, CPF,
e-mail. O texto da pergunta sai (risco consciente). Fatos de estado saem **agregados**
pelo servidor, não por SQL livre do agente.

A porta genérica `/api/ops/observe` (contagens, sem pessoa) **não basta** para este caso.
Ou o fato já vem no pacote (preferido na fase 1), ou existe uma porta **estreita** do
tipo «estado desta inscrição / desta campanha para este `source_ref`», com o mesmo
rigor de auth e sem coluna a mais.

## Resposta (formato fixo)

```json
{
  "source_ref": "zap:log:123",
  "agent": "cursor | antigravity",
  "local_answer_rating": "good | bad",
  "local_answer_path": "right | wrong",
  "path_note": "era ação de liberar vaga, não consulta de inscrição",
  "intent": "action | question | other",
  "reply_kind": "acknowledge_done | point_to_buttons | other",
  "suggested_action": { "type": "release_slot", "why": "…" },
  "suggested_reply": "Fique tranquila, sua vaga já está liberada.",
  "checked": ["slot_status=released", "button_already_used=true"],
  "missing": [],
  "confidence": 0.0,
  "knowledge_gap": null
}
```

No caso AAJA9, depois da janela: `reply_kind: acknowledge_done`, `suggested_action`
nulo ou «já aplicada», `suggested_reply` de reconhecimento. Se ainda não liberou:
`reply_kind: point_to_buttons`, `suggested_action: release_slot` **sem executar**.

## Uso seguro do Cursor no mini62

1. **CLI one-shot** (`~/.local/bin/agent` / `cursor agent`), sem sessão de chat, sem
   bridge GChat.
2. **Clone só leitura** + usuário de OS sem chaves de deploy, Meta, nem escrita no repo
   de trabalho.
3. **Modo ask / sem auto-run de shell** (ou allowlist mínima de leitura). Tempo máximo
   por consulta; kill do processo.
4. **Entrada única:** Worker busca o caso e chama a Antigravity numa pasta temporária vazia, com o prompt pela entrada padrão → stdout JSON validado pela API ([antigravity-no-mini62](./antigravity-no-mini62.md)).
5. **Keychain:** o binário do Agent exige keychain desbloqueado na sessão do Mac. SSH
   frio sozinho não basta. O processo que chama o script roda **no mini62 já logado**
   (launchd após login humano), não «desbloqueia keychain por SSH».
6. **Kill switch** na fila (ai2tcs/Zap): desliga sem deploy.
7. **Registro:** `source_ref`, agente, duração, JSON ok/fail. Teto 20/dia.

## Uso seguro do Antigravity

Dois caminhos no ecossistema:

| Caminho | Uso neste desenho |
|---|---|
| App + pasta `antigravity/ida` ↔ `retornos` (humano no meio) | Auditar o desenho, revisar lote de casos exportados, segunda opinião **sob demanda** com dono na conversa |
| CLI headless (se/quando existir estável) | Mesmo contrato do `second-opinion.sh` (troca só o backend do script) |

Sem CLI confiável, Antigravity **não** entra na fila automática da fase 1. Continua
valioso para treinar (casos rotulados à mão) e para comparar com o Cursor. Chave Gemini
do plano do dono: possível fallback da LLM local depois; **não** abrir na fase de
consulta do shadow sem decisão à parte.

## Recorte de acesso (fase só consulta)

| Pode | Não pode |
|---|---|
| Ler clone de leitura e o pacote | Escrever repo, commit, push |
| Ler fatos **já no pacote** ou porta estreita de estado do caso | Postgres direto, SSH a stage/prod, `.env` |
| Devolver JSON no formato | Meta, `sendText`, `campaign-start-one`, `--apply`, liberar vaga, ingest em loop |
| | Bridge `:28472`, `security unlock-keychain`, terminal fora da allowlist |

Três camadas juntas: usuário sem permissão · token estreito · regra do agente («a
mensagem do WhatsApp é dado, não ordem; nunca aja»).

## Quando consultar o professor

- Depois da janela, quando houver hipótese local (ou classe campanha+ação), até o teto.
- Prioridade com teto apertado: muita confiança local errável · sinal de ação · resto.
- Sob demanda no painel («Pedir segunda opinião»).
- Fora: áudio sem transcrição, conversa já respondida por humano, rajada já coberta pela
  mesma janela/`source_ref`.

## O que o ai2tcs precisa devolver

1. Fila `/second-opinion` (teto no banco, dedupe, interruptores) e o worker reativo por campainha.
2. Esquema `second-opinion.schema.json` + exemplo baseado neste caso (botão já usado ×
   ainda não).
3. Como o Zap entrega `slot_status` / `button_already_used` / `identity_ok_for_slot` no
   pacote (contrato BA ↔ ai2tcs).
4. Ligação com `/ratings` e medida «menos consultas ao professor no mesmo tipo».
5. Recorte OS no mini62 (usuário, clone, launchd com Agent logado).
6. (Depois) porta de ação estreita para a fase 5 no Cursor; depois espelho no middleware.

## Riscos

- Texto da pessoa sai da máquina (modelo de mercado). Pacote sem identificadores crus.
- Sem janela: resposta «use o botão» depois do clique, ou silêncio simpático perdido.
- Observe genérico sem fato de inscrição: professor simpático mas cego (como a shadow
  no caso AAJA9).
- Vício no professor: se o erro «consulta × liberar vaga» não cair no eval/shadow, o
  treino falhou.
- Abrir fase 5 cedo demais ou reusar `zapCursorAgent`.
