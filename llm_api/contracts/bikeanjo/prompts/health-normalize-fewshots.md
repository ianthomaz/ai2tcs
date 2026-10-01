# Few-shots — `healthNormalize` (sem RAG)

Incluir **depois** do system prompt principal (`health-normalize-v1.md`).
Casos alinhados ao `health-normalize.eval.jsonl` e ao ensaio de stage/prod.
O modelo devolve **só** o JSON `response_ok` (sem prosa).

Allowlist: `diabetes` · `hypertension` · `asthma` · `renal` · `tdah` · `tea` · `t21`.

---

### Exemplo A — diabete tipo 1

`known_codes`: `[]` · `free_text`: «diabete tipo 1»

Saída: `codes`: `["diabetes"]`; `outras`: `"tipo 1"`; `generic_statement`: false.
Relatório agrupa por `diabetes`; o tipo fica no resíduo.

---

### Exemplo B — alergia (campo «errado»)

`free_text`: «alergia a dipirona»

Saída: `codes`: `[]`; `outras`: `"alergia a dipirona"` (ou equivalente com
dipirona); **nunca** devolver a allowlist inteira; `generic_statement`: false.

---

### Exemplo C — bronquite ≠ asma

`free_text`: «bronquite»

Saída: `codes`: `[]`; `outras` contém «bronquite»; **não** mapear para `asthma`.

---

### Exemplo D — pressão alta

`free_text`: «pressão alta controlada com remédio»

Saída: `codes`: `["hypertension"]`; `outras` pode manter «controlada com remedio»
(ou null se só o código basta); **não** inventar «usa remédio» se a pessoa não
escreveu «usa».

---

### Exemplo E — declaração genérica

`free_text`: «saude de ferro gracas a deus»

Saída: `codes`: `[]`; `outras`: `null`; `generic_statement`: true.

---

### Exemplo F — elogio + condição

`free_text`: «saude otima, so uma rinite»

Saída: `generic_statement`: false; `outras` contém «rinite»; **sem** «otima» /
«saude otima».

---

### Exemplo G — moldura de frase

`free_text`: «tomo remedio pra ansiedade»

Saída: `codes`: `[]`; `outras` ≈ «remedio pra ansiedade» (sem «tomo»);
`generic_statement`: false.

---

### Exemplo H — TEA já conhecido

`known_codes`: `["tea"]` · `free_text`: «autista leve nivel 1»

Saída: `codes`: `[]` (não repetir tea só por eco); `outras` com o detalhe
(«leve nivel 1» / «autismo leve…») ou null se só repetiu o código;
`generic_statement`: false.

---

### Exemplo I — asma com contexto

`free_text`: «asmatico mas nao tenho crise ha anos»

Saída: `codes`: `["asthma"]`; `outras` null ou detalhe residual sem moldura.
