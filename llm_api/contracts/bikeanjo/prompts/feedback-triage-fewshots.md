# Few-shots — `feedbackTriage` (sem RAG)

Incluir **depois** do system prompt principal (`feedback-triage-v2.md`). Casos
anonimizados alinhados ao `feedback-triage.eval.jsonl`. O modelo devolve só o
JSON de classificação.

---

### Exemplo A — grave

Entrada `fields.recado_livre`: «Um dos monitores ficou fazendo comentários sobre
o meu corpo e me senti muito desconfortável.»

Saída esperada (trecho): tags incluem `grave`; `urgency`: `urgent`;
`anchor_quote` quase literal; `confidence` alta.

---

### Exemplo B — logística + construtiva

Entrada: «Poderiam ter água no local e começar no horário, esperamos 40 minutos.»

Saída: tags `construtiva` e `logistica`; **sem** `grave`; urgency `none` ou `watch`.

---

### Exemplo C — elogio com nome

Entrada: impressão «Amei!» + «A Júlia foi incrível, super paciente comigo.»

Saída: `elogio_pessoa`; `named_people` contém «Júlia»; sem inventar segundo nome.

---

### Exemplo D — elogio vago

Entrada: «Muito bom, obrigado a todos»

Saída: `elogio_geral`; `named_people`: `[]`; **não** marcar `elogio_pessoa`.

---

### Exemplo E — bug de plataforma

Entrada: «O link de confirmação que veio no WhatsApp dava erro e não consegui
escolher o horário.»

Saída: `bug_sistema`; âncora no trecho do erro/link.

---

### Exemplo F — chamado comum (support_ticket)

Entrada `subject`+`message`: voluntariado em Belém.

Saída: tipicamente `outro` (ou construtiva se pedir melhoria); **sem** `grave` /
`bug_sistema` só por ser chamado.

---

### Exemplo G — queda com lesão e conduta (real, 1/out) → grave

Entrada `impressao_curta`: «Eu caí, virei o pé, estou de molho, um pouco deprimida.»
`recado_livre`: «Não foi culpa do instrutor (eu acho), mas ele nem me ajudou a levantar
quando eu caí… eu pedi pra não ir pra rua e já estava querendo parar mas ele insistiu…
hoje é terça e ainda estou com dificuldades pra andar. Estou com medo de voltar.»

Saída: `grave`; `urgency`: `urgent`; âncora no «ele nem me ajudou a levantar» ou no
«ele insistiu». Tom calmo e «não culpo ninguém» **não** baixam a gravidade.

---

### Exemplo H — pedido de mais oferta (real, 1/out) → sem `construtiva`

Entrada `recado_livre`: «A única coisa é que poderia ser mais dias no mês de prática.»
(ou «queria que durasse mais tempo»)

Saída: **sem** `construtiva`; tags só do resto do texto (ex.: `elogio_geral`,
`aprendizado`); `information_value` baixo.

---

### Exemplo I — crítica de equipamento no meio de elogio (real, 1/out) → construtiva

Entrada `recado_livre`: «Gostei muito da experiência… As bicicletas são boas, no
entanto os bancos são um pouco desconfortáveis para mulheres.»

Saída: `construtiva` (+ `elogio_geral`); âncora no trecho dos bancos.
