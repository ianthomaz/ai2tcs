# Avaliação do plano de treinamento (12/nov/2026)

Leitura dos documentos desta pasta contra o código do ai2tcs. A ideia central (agente maior
como professor da LLM local, só consulta no começo, fatos do caso no pacote, teto diário,
medida «precisa cada vez menos do professor») é boa e cabe no que o serviço já tem
(`/ratings`, sinais, critério de envio). Os pontos abaixo mudam **como** fazer.

## 1. O que precisa mudar no desenho

| # | Ponto | Por quê | Proposta |
|---|---|---|---|
| 1 | A rota `POST /second-opinion` chamar `second-opinion.sh` | A API roda no Docker; o `cursor-agent` está no macOS e precisa do keychain da sessão logada. O container não alcança o binário do host. | A API só **enfileira** (tabela, dedupe por `source_ref`, teto e kill switch no banco). Um **worker no host** (launchd na sessão logada) pega o próximo caso por HTTP com token estreito, roda o agente e devolve o JSON. |
| 2 | Wrapper em shell com contador em arquivo | Contador sem trava (duas chamadas juntas passam do teto); o texto da pessoa vai em argumento (`ps` mostra); `timeout` não existe no macOS sem coreutils; não valida o JSON. | Worker em Python no repo: prompt por stdin, timeout do próprio processo, validação pelo esquema, teto contado no banco. |
| 3 | Passo 3: resposta do professor vira exemplo `great` sozinha | A LLM aprenderia com respostas que ninguém conferiu, contra o princípio de `/ratings` (aprovação de pessoa). | Julgamento do professor entra em `/ratings` marcado `rater: teacher`; vira exemplo só quando uma pessoa confirma (ou, decidido pelo dono, quando professor e pessoa concordam). |
| 4 | Cursor «consulta o banco / enxerga o estado real» (fases § 3) | Contradiz o resto da pasta (fatos só no pacote, sem SQL). | Fica a regra da pasta: fatos já resolvidos pelo cliente no pacote; porta estreita só se o pacote não bastar. |
| 5 | Teto: 20 em três documentos, 30 em outros dois | Mesmo número, valores diferentes. | Um só valor por configuração (`SECOND_OPINION_DAILY_LIMIT`), padrão 20; o fim de semana sobe por configuração. |

## 2. Ordem que proponho no ai2tcs

1. **Higiene do eval** ([higiene-eval-ask.md](./higiene-eval-ask.md)): classificar
   `eval_questions.json` nos baldes A–D e o portão medir cada balde à parte. Não depende
   de agente nenhum e diz se o RAG melhora de verdade.
2. **Fila da segunda opinião**: tabela, `POST /second-opinion` (enfileira), retirada pelo
   worker, devolução validada pelo esquema, teto, kill switch, `GET` do resultado.
3. **Worker do mini62** com o Cursor como primeiro backend (o Antigravity entra pelo mesmo
   contrato quando tiver modo sem tela).
4. **`/ratings` com `rater`** (pessoa ou professor) e a conta «concordância local ×
   professor» por tipo de caso.
5. Lado Bike Anjo (janela de ~2 min, fatos do caso, caixa no painel): depois, pelo contrato.

## 3. Ajustes de texto na pasta

- «Régua» em `fases-e-cotas-fins-de-semana.md` § 2 → «teto»; números de teto alinhados ao
  item 5 acima quando a fila existir.
