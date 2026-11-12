# Avaliação do plano de treinamento (12/nov/2026)

Leitura dos documentos desta pasta contra o código dos dois lados: quem pede (Bike Anjo,
`zapzap`) e quem trata (ai2tcs). Lente: o Bike Anjo é o estudo de caso e o WhatsApp o
primeiro canal, mas o que nasce no ai2tcs serve a qualquer projeto e canal (suporte,
e-mail, formulário).

## 1. O que o plano acerta

Agente maior como **professor**, não substituto; só consulta no começo; fatos do caso
resolvidos pelo cliente e mandados no pacote; teto diário e interruptor; medida «precisar
cada vez menos do professor»; proibição do `zapCursorAgent`; higiene do eval antes de mexer
em flag.

## 2. O que muda no desenho (feito no código em 12/nov)

| # | Ponto do plano | Problema | Como ficou |
|---|---|---|---|
| 1 | Rota da API chama `second-opinion.sh` | A API roda no Docker; o agente está no macOS e precisa da sessão logada | A API só enfileira; um **worker no host** busca o caso e devolve a saída ([26](../26-second-opinion.md)) |
| 2 | Wrapper em shell | Contador em arquivo sem trava; texto da pessoa em argumento (visível em `ps`); `timeout` não existe no macOS; resposta não validada | Worker em Python: prompt na entrada padrão, pasta vazia, ambiente mínimo, tempo máximo; teto contado no banco dentro da transação; a API valida a resposta |
| 3 | Contrato preso ao caso da vaga (`slot_status`, `release_slot`, `campaign_kind` em lista fixa) | Outro projeto ou canal não cabe | `case_facts` e `context` são do projeto; `allowed_actions` é a lista fechada **do pedido**; `channel` e `case_kind` identificam canal e tipo; `reply_kind` genérico (`point_to_ui` no lugar de `point_to_buttons`) |
| 4 | Resposta do professor vira exemplo `great` sozinha (passo 3 do roteiro) | A LLM aprenderia com resposta que ninguém conferiu | A opinião fica em `second_opinions`; só a nota de uma pessoa vai a `/ratings` |
| 5 | «O Cursor consulta o banco / vê o estado real» (fases § 3) | Contradiz o resto da pasta | Vale a regra da pasta: o professor não usa ferramenta; fato fora do pacote vai em `missing` |
| 6 | Teto 20 em uns documentos, 30 em outros | — | Um valor: `SECOND_OPINION_DAILY_LIMIT` (20), todos os projetos juntos; o fim de semana sobe por configuração |
| 7 | Texto da pessoa vai cru ao modelo de mercado | E-mail e telefone escritos na mensagem saem da máquina | O serviço troca e-mail, CPF e número com cara de telefone por `[contato]` / `[documento]` antes de guardar |
| 8 | Tom («acolhe e encerra, sem papo furado») espalhado em prompts | — | Regras gerais no prompt fixo do professor; o tom do projeto em `config_json.second_opinion.teacher_notes` |

## 3. Higiene do eval (feito)

O `5/85` vinha sobretudo de a pontuação contar **silêncio como erro**: 45 dos 85 casos do
Bike Anjo são ruído (saudação, emoji, mídia, resposta automática de terceiros), em que o
certo é não responder. Cada caso tem agora `bucket`, pontuado pelo que é «bom» nele, e o
portão mostra a conta por tipo:

| `bucket` | Passa quando | Casos BA |
|---|---|---|
| `org_factual` | resposta dentro das palavras-chave | 22 |
| `org_link` | idem (pedido de link, cadastro, acesso) | 11 |
| `user_system` | `intent.knowledge_kind = user_system` e nenhuma prosa | 2 |
| `silence` | nenhuma resposta | 45 |
| `unsorted` | fora do portão até alguém classificar | 5 |

A classificação é uma primeira passada; quem conhece os casos revê em
`llm_api/tests/eval/eval_questions.json`. A referência do portão (`--save-baseline`)
grava-se de novo depois do deploy.

## 4. O que o lado que pede já tem (Bike Anjo) e o plano não usa

O caso canônico (resposta em prosa a uma campanha de confirmação) **já tem porta** no
Zap: `lib/reply-reader.js` + `reply-expectation.js` (`event_confirmation` lê
`confirm_presence` / `release_slot` / `escalate_human`), com janela de ação da campanha
(`campaign-action-window.js`) e linha própria no shadow (`SHADOW_REPLY_READING`). A
hipótese errada do caso AAJA9 veio do **outro** caminho (roteador + `/ask`), que tratou a
mesma mensagem como conversa.

Consequências para o lado Bike Anjo, quando for a vez dele:

1. Mensagem dentro da janela de uma campanha: a «resposta local» do pacote é a **leitura**
   do `reply-reader`, e `case_kind` é o contexto dela (`event_confirmation`). O `/ask` não
   gera hipótese de conversa para essa mensagem.
2. `allowed_actions` do pacote = as leituras do catálogo daquele contexto.
3. Fatos do caso (`slot_status`, botão usado, identidade) saem de quem já resolve a janela
   de ação; o debounce de ~2 min é do Zap.
4. Suporte e e-mail entram depois pelo mesmo `POST /second-opinion`, com `channel: ticket`
   ou `email` e o `case_kind` deles; nada muda no ai2tcs.

## 5. Ordem daqui em diante

1. Deploy do ai2tcs; no mini62, `second_opinion_worker.py --dry-run` para achar o comando do
   Cursor que responde sem tela e sem ferramenta (fase 0 do plano).
2. Casos de prova (2 ou 3 do tipo AAJA9) enfileirados à mão com a chave do projeto.
3. Lado Bike Anjo: pacote a partir do `reply-reader` e caixa da opinião no `/adm/shadow-llm`.
4. Com um fim de semana medido (`GET /second-opinion/stats`): filtro do que não vale
   consultar, pelos sinais que o serviço já devolve.

## 6. Em aberto

- Comando exato do Cursor sem tela e sem ferramentas: só se confere no mini62.
- Antigravity na fila automática: quando tiver modo sem tela; até lá, auditoria de lote.
- Exemplo aprovado quando professor e pessoa concordam, sem a pessoa digitar a resposta:
  decisão do dono depois do primeiro fim de semana medido.
