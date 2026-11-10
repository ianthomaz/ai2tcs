# 21 — Avaliação de nov/2026: prioridades do Bike Anjo e revisão de arquitetura

Leitura, contra o código da `main` de 10/nov/2026, de dois documentos da raiz:

- [`prioridades_paraBikeAnjo.md`](../prioridades_paraBikeAnjo.md) — S1 a S4, pedido do Bike Anjo;
- [`AVALIACAO_ARQUITETURA_E_ECOSSISTEMA_ITCS.md`](../AVALIACAO_ARQUITETURA_E_ECOSSISTEMA_ITCS.md) — § 1.2 (pontos técnicos), § 3.2 e § 5.

Critério de todo o plano: o que entra no ai2tcs é **genérico** (vale para qualquer projeto
por configuração; ver [README § Princípio](../README.md#princípio-serviço-de-vários-projetos))
e vai em fatias pequenas, cada uma com teste e prova (§ 5.1 da avaliação).

---

## 1. O que o código mostra

| Item | Diz o documento | O código | Situação |
|---|---|---|---|
| § 1.2.1 dedup do `/ask` | hash só de `project_id` + pergunta | `app/api/ask.py` `_question_hash`: confirmado. O zapzap manda `user_id`, `user_context` e `history`; duas pessoas com a mesma pergunta em 10 min recebem o **mesmo job**, com a resposta personalizada da primeira | **defeito real** |
| § 1.2.2 `id_contato` | `hasattr` sempre falso | confirmado; o ramo nunca roda. Ninguém manda `id_contato` (o zapzap manda `user_id`) | código morto: tirar |
| § 1.2.3 rerank | não corta | `_rerank_for_diversity` devolve `selected + deferred` (mesmo total) | otimização, depende do `eval_gate` |
| § 1.2.4 monitor | manifesto olha `/` | `itcsManifest.yaml` → `https://llm.webplace.cc/`, espera 200 | troca barata para `/health` |
| S1 confiança do `/ask` | `/ask` não tem confiança | `/result` já devolve `signals` (melhor distância, trechos, trava, tokens), e o `/adm/shadow-llm` mostra a pílula. Não há **um número** nem medida de quanto a resposta se apoia nos trechos | parcial |
| S2 `healthNormalize` v2 | v1 só lê condições | **desatualizado:** o sistemaBA (`health-normalize-shared.ts`) já manda alergias, limitações e condições num texto só (`health-v2`), e `generic_statement` cobre «só disse que está bem». O que não existe é a resposta separada por campo | quase feito |
| S3 aprendizado do shadow | ingestão manual | `tools/scripts/shadow-learn-to-ai2tcs.sh` (Bike Anjo) roda no deploy: julgamentos → `import_eval_set.py` (eval) + `37_shadow_aprendizado_deploy.md` (corpus). Não existe porta no ai2tcs nem aprendizado que mude a geração | aberto |
| S4 histórico na triagem | prompt ignora `historico.*` | confirmado: `feedback-triage-v2.md` não fala de `historico.*`, embora o sistemaBA mande | aberto |

## 2. Plano em fatias

Cada fatia é um commit nos dois repositórios quando muda contrato; nenhuma precisa de banco
novo nem de migration.

| Fatia | O quê | Onde | Tamanho |
|---|---|---|---|
| **F0** | dedup do `/ask` passa a incluir quem pergunta e o contexto (`user_id`, hash de `user_context`, `history`, `system_prompt`); sai o ramo `id_contato`; monitor do manifesto em `/health` | ai2tcs `api/ask.py`, `itcsManifest.yaml` | pequeno |
| **F1 (S1)** | `signals.grounding` determinístico: fração das palavras de conteúdo e dos links da resposta que aparecem nos trechos; `signals.unsupported_links` (link fora dos trechos e da allowlist); `signals.answer_confidence` 0–1 composto só dos sinais (nunca autodeclarado). Calibração com a tabela confiança × nota do shadow | ai2tcs `llm/signals.py`, contrato `ask.schema.json`; Bike Anjo: pílula do `/adm/shadow-llm` usa o número do `/ask` para a hipótese do `/ask` | médio |
| **F2 (S4)** | `triage-v3`: o prompt usa `historico.*` para ler evolução (dificuldade antes + relato de avanço hoje → `aprendizado`); casos novos no `feedback-triage.eval.jsonl` | prompt nos dois repos, `prompt_version` novo | pequeno |
| **F3 (S3)** | porta genérica de julgamentos: o projeto manda o julgamento (pergunta, resposta, nota, motivo); o ai2tcs vira caso de eval, **propõe** padrão proibido a partir dos motivos (`link_inventado`, `prometeu_fora_da_regra`) e guarda respostas `great` como exemplo para few-shot no `/ask` (§ 3.2.1 da avaliação) | ai2tcs nova porta + `config_json`; Bike Anjo: o script do deploy passa a chamar a porta | médio a grande |
| **F4 (S2)** | resposta por campo (`allergies`, `limitations`, `conditions`) no `health-v3` | os dois repos | pequeno |

Fora deste ramo (não é demanda do Bike Anjo e a avaliação manda fatiar): MCP do ecossistema
(§ 2), fila offline (§ 3.1), `/edu` (§ 3.2.3), prefill no `/router` (§ 4.3), corte de
trechos do rerank (§ 1.2.3, só com `eval_gate`).

## 3. Decisões do dono

- **F3:** padrão proibido aprendido entra sozinho na geração, ou fica como proposta até o
  operador aprovar? Recomendação: aprovar primeiro, coerente com «nada responde nem executa
  sem aprovação no `/adm/shadow-llm`».
- **F2:** S4 pede `answer_solidity: 5` no caso «medo antes + nota 5». Hoje `answer_solidity` mede
  coerência entre escalas e texto. Recomendação: o histórico entra na leitura de **impacto**
  (tag `aprendizado`, `information_value`), e `answer_solidity` mantém o sentido.
- **F4:** fazer agora ou esperar caso real de resíduo misturado entre campos. Recomendação: esperar.

---

**Anterior:** [20-text-tasks.md](./20-text-tasks.md)
