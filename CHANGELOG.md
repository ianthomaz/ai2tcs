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
4. **Base do Bike Anjo, nesta ordem:**
   1. `python scripts/eval_gate.py --project bikeanjoall_2026 --save-baseline` (a referência de hoje);
   2. `scripts/seed_bikeanjoall.py` (leva `retrieval_hints`, `num_ctx`, `tasks`; o seed troca
      o `config_json` inteiro, mas mantém os termos aprovados em `/ratings`);
   3. ingest do projeto (o corte novo dos trechos só vale depois dele);
   4. `python scripts/eval_gate.py --project bikeanjoall_2026` (compara com a referência); piorou, volta o
      `config_json` anterior e avisa.
5. Outros projetos: o corte novo vale no próximo ingest de cada um; comparar com o portão.
6. Sem variável de ambiente nova.

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
- **Busca:** `config_json.retrieval_hints` (o que o canal prefere: sobe, desce, exclui,
  grupos de palavras-chave), lido pelo `/ask` e pelo `/router`; `policies.embedding_query_instruction`
  (instrução de busca do modelo de embedding na pergunta, desligada). [docs/12 § Busca](docs/12-llm-fleet-rag-operations.md#busca-como-um-trecho-chega-ao-prompt)

- **`policies.retrieval_query_with_history`:** pergunta curta de continuação busca junto com
  a pergunta anterior da pessoa (desligada; [docs/08](docs/08-project-config.md)).

### Muda

- **`policies.rated_examples` chega ao `/ask`:** a política nunca saía de `get_rag_policies`
  (que devolve um conjunto fixo); agora sai, de 0 a 5.
- **Dashboard:** sessão vale 24 h no servidor; login Google exige e-mail verificado; cookie
  `secure` em https; senha, `state` e token global comparados em tempo constante.
- **Áudio `.webm`** reconhecido pela assinatura (nada passa a ser recusado).

- **Corte dos trechos no ingest:** nenhum trecho passa de `chunk_size` (parágrafo longo é
  cortado no fim de frase), todo pedaço de seção longa começa com o título da seção, e a
  sobreposição configurada (`chunk_overlap`) passa a acontecer. Vale no próximo ingest.
- **Busca:** cada índice entrega 2 × `top_k` candidatos antes do corte (a reordenação tem de
  onde escolher); a palavra-chave ignora acento e pontuação.
- **`signals.unsupported_links`:** link que vem só de um exemplo aprovado não conta como visto.
- **`/ask`:** pergunta repetida só vira o mesmo job quando quem pergunta e o contexto enviado
  (perfil, histórico, prompt, modelo, callback) são os mesmos. Duas pessoas com a mesma
  pergunta recebem cada uma a sua resposta.
- **`/health`:** o corpo (público) não traz texto de erro; o erro vai para o log.
- **Seed do Bike Anjo:** soma os termos aprovados em `/ratings` aos da configuração.
- **Docs:** os dois documentos da raiz (revisão de arquitetura e prioridades do Bike Anjo)
  viram [docs/23](docs/23-ecosystem-panorama.md) e [docs/21](docs/21-review-nov2026.md). Os planos
  antigos (00, UPGRADES, 11, 13, 16, 17) marcam o que está feito e apontam para a lista única
  do que segue aberto, [docs/23 § 8](docs/23-ecosystem-panorama.md#8-roteiro-único-do-ai2tcs).
- **Triagem do Bike Anjo (`triage-v2`):** regra 10, o histórico da mesma pessoa
  (`historico.*`) conta como evolução; o nome da versão fica.
- **Contrato do Bike Anjo** sincronizado (`contracts/bikeanjo/ORIGIN.md`): o prompt de saúde lê
  alergias, limitações e condições juntas.
