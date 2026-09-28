# Few-shots — `feedbackTriage` (sem RAG)

Incluir **depois** do system prompt principal (`feedback-triage-v1.md`). Casos
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
