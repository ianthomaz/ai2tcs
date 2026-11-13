# Passagem de sessão: segunda opinião e shadow (13/nov/2026)

Para o agente que continua o trabalho. Sai deste arquivo quando os itens do § 4 fecharem.

## 1. Ramos

| Repositório | Ramo | Último commit |
|---|---|---|
| `ianthomaz/ai2tcs` | `claude/bike-anjo-llm-integration-7fsuhp` | `docs(antigravity): open item on macOS folder access` |
| `ianthomaz/bikeanjo2026all` | `claude/bike-anjo-llm-integration-7fsuhp` | `docs(10h): chamados entram na segunda opinião` |

O trabalho segue no `claude/adoring-ride-s7vtld` (nos dois repositórios), que contém todo o `7fsuhp`.

Nada foi para o ar. Deploy só com a frase do dono. Commit e push no ramo são parte do trabalho.

## 2. O que está feito (código + testes, desligado)

**ai2tcs**
- Fila `/second-opinion` ([26](../26-second-opinion.md)): interruptor do serviço, do projeto e teto de 20/dia;
  aceita `subject_ref` (id da pessoa, nunca telefone), que vai só para o worker.
- Worker do Mac `llm_api/scripts/second_opinion_worker.py`: `--listen` (campainha 127.0.0.1:9191),
  `--once`, `--dry-run`, `--try caso.json --project id` (um caso sem API); consulta só leitura
  (`PROD_READONLY_URL` + `PROD_READONLY_KEY` em `local-only/credentials/{projeto}.env`); pausa por
  `local-only/DISABLE_SECOND_OPINION`; variáveis em `local-only/second_opinion_worker.env`; launchd de exemplo.
- Professor = **Antigravity** ([antigravity-no-mini62](./antigravity-no-mini62.md)): prompt traz regras do
  professor, regras da casa e diretrizes do projeto; ela não recebe chave nem pasta.
- Uma pasta por projeto `llm_api/project_library/{id}/` ([27](../27-projetos-e-aprendizado.md)); casos de
  avaliação em `casos/`; regras da casa em `_shared/`.

**Bike Anjo**
- viewLLM `GET /api/llm/view` (`sistemaBA/src/lib/llm-view.ts`): visões `case`, `person`, `events-open`;
  chave `LLM_VIEW_READ_TOKEN` (AC6 no 06c, pendente); sem dado pessoal.
- Regras do robô quando falar (07b § Regras do robô): 2 respostas resolvem, a 3ª aponta o site.

## 3. Desenho fechado com o dono nesta conversa

1. O shadow é **um só** para todas as portas (Zap, chamados `/admin/suporte`, pergunta manual).
   A Antigravity é uma **segunda camada dentro do mesmo shadow**: dá o rate dela à hipótese da LLM local.
2. **Duas linhas de nota no mesmo registro:** a da Antigravity (mesma escala ⛔ 👎 👍 👍👍) e a humana.
3. **O dono lê uma resposta só:** se a Antigravity passou, a dela (marcada «Antigravity»); senão, a da
   LLM local (marcada «LLM local»). Ele avalia o que leu. Nota boa dele na resposta da Antigravity
   vira exemplo da LLM local (óbvio; não perguntar).
4. **Pergunta manual no sistema:** espera o fluxo completo e mostra tudo junto.
5. Mensagens que chegam sozinhas (Zap e chamados) ganham o rate na hora, até o teto do dia.
6. Saúde (normalização) **não** entra neste trabalho. Feedback é outra conversa.

## 4. Em aberto

1. **Sugestão de ação no `/adm/shadow-llm`** aparece como JSON cru (`zapzap/app/adm/shadow-llm/page.tsx`,
   bloco `suggested_action`; origem `zapzap/lib/suggested-action.js`). O dono quer frase. Proposta
   feita, **sem resposta do dono**: a LLM só reconhece o pedido; o sistema consulta o banco e o texto
   sai de frase fixa preenchida (situação da inscrição com posição na fila, confirmar presença,
   liberar vaga). Na tela: ação · o que o sistema encontrou · resposta que sairia. Textos passam pelo dono.
   A viewLLM ainda não traz `waitlist_position`.
2. **Ver os casos reais da sugestão de ação pelo Observer** de produção e stage. O ambiente
   «SistemaBA2» já tem as chaves (`sistema.bikeanjo.org` e `sistema.2trythis.com`, `Authorization`).
3. **Zap e chamados mandarem o caso** ao `POST /second-opinion` (com `subject_ref` = `user_id`) e a
   **opinião aparecer na tela** com as duas linhas de nota (C13 no docs/16 do Bike Anjo).
4. **mini62, com o dono na frente:** `--dry-run` da Antigravity (abre janela? responde sem tela?),
   acesso à pasta Documentos (cópia fora de Documentos ou acesso a um executável só), três casos
   pelo `--try`.
5. Bateria do Bike Anjo: `participation-status-write-guard.test.ts` falha por `lib/event-virtual-rsvp.ts`
   (veio da main; não é deste trabalho).

## 4a. Leitura do Observer e do código (13/nov)

Observer de produção, 14 dias: 76 hipóteses no shadow, 46 marcadas `event_interest_lookup`, 30 `/ask`;
1 com `send_gate`, 0 com `answer_confidence`; 12 notas humanas (10 sem nota). Stage: shadow vazio.

A consulta `zapzap/lib/event-interest-lookup.js` **não entrega a situação real** da pessoa:

1. Todo erro de consulta vira «não encontrei registros» (cada `catch` devolve vazio). Falha de banco
   e pessoa sem inscrição saem com a mesma frase, e o log não guarda o erro.
2. Telefone de 12 dígitos (WhatsApp sem o 9) não gera a variante com o 9: quem tem `users.phone`
   com 11 dígitos não é achado.
3. Sem `event_id` dito pela LLM, o evento sai só de convite de campanha dos últimos 14 dias. A
   inscrição da pessoa em data aberta não é consultada.
4. Achou: frase única «não confirmamos a inscrição ainda», para qualquer `participation_status`.
   `waitlist_position` não é lido.
5. Lista fechada do `/ask` (`seed_bikeanjoall.py`): `event_interest_lookup` e duas reservadas
   (`registration_completeness_lookup`, `city_event_lookup`) que o Zap só registra e cala.
   Confirmar presença e liberar vaga não existem na lista.

## 4b. Ensaio: leitura da pessoa (13/nov, no ramo, sem deploy)

Regra do dono: tudo isto é ensaio, 100% shadow. Nada muda a resposta do WhatsApp nem dos chamados,
e nada escreve em dado de usuário.

- Bike Anjo: `zapzap/lib/shadow-person-reading.js` parte da pessoa (conta pelo telefone, inscrições
  em datas abertas, situação, posição na espera) e grava `person_reading` no shadow; a tela mostra
  ação · o que o sistema encontrou · rascunho da resposta. Observer `zap-shadow` ganhou `actions` e
  `personReadings`. Documento: 07b § Leitura da pessoa no ensaio.
- A consulta live `event-interest-lookup.js` segue intocada (defeitos listados no § 4a).
- Falta: textos do rascunho com o dono; chamados com a mesma leitura; Zap e chamados mandarem o
  caso à fila `/second-opinion`.

## 5. Como o dono quer as mensagens

pt-BR, numeradas de 1 a N em cada mensagem, um assunto = um número com a pergunta dentro (saídas
a/b e recomendação). Curto. Nunca pergunta óbvia. Nada de mexer quando ele diz «conversa».
