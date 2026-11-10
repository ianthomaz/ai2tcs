# Changelog

O que muda no serviço, por publicação. Cada entrada diz o que muda para quem chama a API e,
em **Atenção no deploy**, o que precisa acontecer no servidor para valer. A seção
«Não publicado» é o que está na `main` (ou no ramo aberto) e ainda não subiu no mini62; no
deploy ela ganha a data e começa outra vazia.

## Não publicado

### Atenção no deploy

1. **Antes do `git pull` no mini62:** `git status`; se houver arquivo mexido no servidor,
   `git stash` (e conferir com `git stash show -p`; a versão do git é a que vale).
2. **Migration nova** `20261110120000_answer_ratings` (tabelas `answer_ratings` e
   `rating_proposals`). Entra sozinha no `prisma migrate deploy` ao subir o container.
   Conferir: `SELECT count(*) FROM answer_ratings;` responde (0 no começo).
3. **Subir junto com o Bike Anjo** (`bikeanjo2026all`, mesmo ramo). Os dois lados usam o
   mesmo contrato (`contracts/bikeanjo/`); separado, o painel do Zap fica sem propostas e sem
   a confiança da resposta.
4. Sem variável de ambiente nova.

### Novo

- **`/ratings`** ([docs/22](docs/22-answer-ratings.md)): o projeto manda julgamentos de
  resposta. Resposta reprovada propõe termo proibido, que só vale depois que uma pessoa aprova
  (`POST /ratings/proposals/{id}/decision`) e então entra em `policies.forbidden_terms`.
  Resposta «ótima» vira exemplo no `/ask` quando o projeto liga `policies.rated_examples`
  (padrão desligado).
- **`signals` do `/ask` e do `/router`:** `grounding` (quanto do texto os trechos apoiam),
  `unsupported_links` (link que o modelo não viu), `answer_confidence` (0–1, só dos sinais) e
  `confidence_basis` (`signals-v1`). Campos aditivos ([docs/02](docs/02-api-integration.md)).
- **`GET /health?strict=1`:** 503 quando degradado; o `itcsManifest.yaml` monitora por aí.

### Muda

- **`/ask`:** pergunta repetida só vira o mesmo job quando quem pergunta e o contexto enviado
  (perfil, histórico, prompt, modelo, callback) são os mesmos. Duas pessoas com a mesma
  pergunta recebem cada uma a sua resposta.
- **`/health`:** o corpo (público) não traz texto de erro; o erro vai para o log.
- **Triagem do Bike Anjo (`triage-v2`):** regra 10, o histórico da mesma pessoa
  (`historico.*`) conta como evolução; o nome da versão fica.
- **Contrato do Bike Anjo** sincronizado (`contracts/bikeanjo/ORIGIN.md`): o prompt de saúde lê
  alergias, limitações e condições juntas.
