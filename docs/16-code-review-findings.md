# 16 — Avaliação de código: achados e dúvidas em aberto

Achados levantados durante o trabalho de contexto rico do Bike Anjo (jul/2026). Separa
o que foi tratado do que ficou em aberto, e regista as dúvidas que impedem decidir.

**Anterior:** [15-cross-project-fixes.md](./15-cross-project-fixes.md) · **Seguinte:** [01-overview.md](./01-overview.md)

---

## Como ler este documento

Cada achado tem três partes: **o que o código faz** (verificado executando, não por
leitura), **o que acontece** em consequência, e **dúvidas** — o que não dá para
responder de dentro deste repo.

As dúvidas são a parte útil. Vários achados só são defeito sob uma leitura da
intenção, e a intenção não está no código. Nada da secção 1 foi alterado.

---

## 1. Em aberto — nada foi alterado

### 1.1 O dedup do `/ask` não distingue contatos

**O que o código faz.** A chave de dedup usa projeto e texto da pergunta
(`llm_api/app/api/ask.py:21`):

```python
def _question_hash(project_id: str, question: str) -> str:
    normalized = " ".join(question.strip().lower().split())
    return hashlib.sha256(f"{project_id}:{normalized}".encode()).hexdigest()
```

A busca filtra pelos mesmos dois campos e mais nada
(`llm_api/app/db.py:379`):

```sql
WHERE project_id = $1 AND question_hash = $2
  AND created_at > NOW() - ($3::text || ' seconds')::interval
```

Janela padrão 600s (`llm_api/app/registry.py:73`); o project `bikeanjoall_2026` não
sobrescreve. Verificado: duas chamadas com contatos diferentes e a mesma frase
produzem hash idêntico.

**O que acontece.** Dentro da janela, o segundo contato recebe o `job_id` do
primeiro. `/result/{job_id}` devolve a resposta gerada com o `user_context` do
primeiro — cidade, interesse, nome, jornada.

O peso disto mudou com o [§1.1 do contrato Bike Anjo](../10d_ai2tcs_contrato_e_evolucao.md).
Enquanto o contexto rico não chegava ao prompt, as respostas eram genéricas e
reaproveitar job entre contatos era quase inócuo. Com cidade e interesse a moldar a
resposta, o mesmo mecanismo passa a devolver resposta personalizada de outra pessoa.

**Dúvidas.**

- Qual o propósito do dedup? Absorver rajada do mesmo contato e servir de cache
  entre contatos são desenhos diferentes; o comportamento actual só é defeito num deles.
- O zap chega a chamar `/ask` duas vezes para a mesma pergunta, ou já deduplica do
  lado dele? Se já deduplica, isto pode nunca disparar em produção.
- 600s foi escolhido ou é o default herdado?
- Qual a taxa real de colisão no tráfego? Frases como "tem evento na minha cidade?"
  repetem-se entre pessoas, mas a frequência só se estima com o log.

### 1.2 `id_contato` é lido mas nunca existe

**O que o código faz.** Em `llm_api/app/api/ask.py:64`:

```python
user_id=request.id_contato if hasattr(request, "id_contato") else request.user_id,
```

`AskRequest` (`llm_api/app/models.py:55`) não declara `id_contato` e não define
`extra`, pelo que vale o `ignore` padrão do pydantic. Verificado construindo um
`AskRequest` com `id_contato` preenchido:

| Verificação | Resultado |
|---|---|
| `id_contato` em `AskRequest.model_fields` | `False` |
| `hasattr(request, "id_contato")` | `False` |
| valor resolvido para `user_id` | `None` |
| `model_config["extra"]` | default (`ignore`) |

O ramo é morto: `hasattr` é sempre falso, e o campo enviado no corpo é descartado
antes de virar atributo.

**O que acontece.** Depende do nome que o zap usa. Se envia `user_id`, a linha é
código morto inofensivo. Se envia `id_contato`, `user_id` fica `None` em todas as
chamadas e o bloco `if user_id:` de `run_rag_job` nunca corre: sem histórico do
banco, sem perfil do banco, sem gravar a conversa. O `user_context` do request
continua a funcionar, pelo que a resposta não parece quebrada — fica sem memória,
em silêncio.

**Dúvidas.**

- **Qual dos dois nomes o zap envia?** É o que decide se isto é código morto ou
  personalização desligada em produção.
- O `hasattr` foi escrito por algum motivo. Houve um período em que `id_contato`
  chegava? Foi renomeado de um lado só?
- Se `user_id` é `None` hoje, o histórico que o modelo vê vem apenas do `history`
  enviado pelo zap — o que pode ser exactamente o desenho pretendido.
- Interage com [1.1](#11-o-dedup-do-ask-não-distingue-contatos): se `user_id` é
  `None` para todo o tráfego, não há por onde separar o dedup por contato.

### 1.3 `_rerank_for_diversity` reordena, não corta

**O que o código faz.** `llm_api/app/jobs/worker.py:45`. A docstring descreve o
problema como desperdício de janela de contexto e a solução como *"keep at most
max_per_doc chunks per source document"*. A implementação termina em
`return selected + deferred`: o que excede a cota vai para o fim da lista, não é
descartado. Verificado com `max_per_doc=2`:

| | |
|---|---|
| chunks à entrada | 6 (5 de `doc_A`, 1 de `doc_B`) |
| chunks à saída | 6 |
| de `doc_A` à saída | 5 |

`build_messages` monta o contexto com todos os chunks recebidos, e a chamada em
`worker.py:324` é o último passo antes do uso — não há corte posterior.

**O que acontece.** Os chunks redundantes continuam a chegar ao prompt; o que a
função entrega é ordem. O desperdício descrito na própria docstring mantém-se.
No mesmo bloco convivem uma docstring que diz cortar e um comentário que diz
*"This preserves the original total count"*.

**Dúvidas.**

- A intenção era cortar ou reordenar? Se reordenar, a docstring descreve ambição,
  não código. Se cortar, falta o corte.
- Cortar mudaria o prompt de **todos** os projetos, não só do Bike Anjo. Não se sabe
  daqui quanto os outros dependem de receber os chunks todos.
- Se o incómodo original era o modelo ancorar-se no primeiro chunk, reordenar por si
  já resolve e não falta nada.
- `max_per_doc=2` está fixo no default, sem override por projeto — escolha ou
  ausência de necessidade?

### 1.4 Login do dashboard

Quatro pontos no mesmo território. O risco de cada um depende de como o serviço está
exposto, o que não se vê deste repo.

| # | Onde | O que se verificou |
|---|---|---|
| a | `llm_api/app/dashboard/routes.py:24` | `_sessions: set[str]` sem timestamp. Só `add`, `discard` no logout e teste de pertença; nenhuma expiração. O `max_age=86400` do cookie é instrução ao navegador — o servidor aceita o id enquanto o processo viver |
| b | `llm_api/app/dashboard/google_oauth.py:53` | `fetch_google_email` lê `email` e ignora `email_verified`, que não aparece em nenhum ponto de `app/`. O email é a identidade do allowlist (`routes.py:243`) |
| c | `routes.py:257` e `297` | `set_cookie` com `httponly=True` e `samesite="lax"`, sem `secure=True` |
| d | `routes.py:284`, `llm_api/app/auth.py:27` | Segredos comparados com `!=` / `==` simples, não em tempo constante |

**Dúvidas.**

- Com que frequência o processo reinicia? Reinício frequente funciona como expiração
  de facto e torna (a) teórico.
- O allowlist tem apenas endereços de um domínio Workspace controlado? Se sim, a
  distinção entre email verificado e não verificado deixa de existir na prática.
- O serviço atende em http nalgum cenário — rede interna, Tailscale, acesso directo
  ao container? Se todo o acesso é https na borda, (c) não tem por onde se manifestar.
- Dashboard e API estão atrás de Cloudflare Access? Existe rate limit no
  `POST /dashboard/login`? Não há nenhum no código, mas pode estar na borda.

---

## 2. Já tratado — contexto para quem ler os commits

Alterado na branch de contexto rico, com o motivo:

| Achado | Onde | Tratamento |
|---|---|---|
| Fallback genérico mandava convidar para contato quando o RAG vinha fraco, contra o P6 | `scripts/seed_bikeanjoall.py` | `no_answer_fallback` próprio do project |
| Projeto herdava `message_size: medium` = 2 a 4 parágrafos, num canal de WhatsApp | idem | `llm_options` com `short` e `direct` |
| `prompt.py:51` manda personalizar e tratar pelo nome, contra o §3 do contrato | idem | Regra contrária no `system_instruction`, que é anexado por último e vence — sem tocar na linha partilhada |
| Contexto de plataforma renderizado como chave crua (`journey_kind: pofr`) | `app/rag/prompt.py` | `profile_display` opcional (labels, glossary). Sem config o render é byte a byte o de antes |
| `/router` recuperava só pela mensagem, pelo que o mapa de fluxos raramente voltava | `app/api/message_router.py` | Query de retrieval leva cidade, interesse, jornada e evento. Sem esses campos, query inalterada |
| `clearance` (NOIA) no prompt é sinal de autorização | ambos | Fora do prompt; ver §1.2 do [contrato](../10d_ai2tcs_contrato_e_evolucao.md) |
| `journey_destination` tratado como caminho de URL, quando via de regra é referência interna | ambos | Só entra no prompt se já for URL absoluta; ver §1.3 do contrato |

---

## 3. As três perguntas que decidem o resto

1. **O zap envia `user_id` ou `id_contato`?** Decide se [1.2](#12-id_contato-é-lido-mas-nunca-existe)
   é código morto ou personalização desligada, e condiciona [1.1](#11-o-dedup-do-ask-não-distingue-contatos).
2. **Para que serve o dedup?** Rajada do mesmo contato ou cache entre contatos são
   desenhos diferentes, e o comportamento actual só é defeito num deles.
3. **A rerank devia cortar?** A docstring e o comentário no mesmo bloco discordam.
