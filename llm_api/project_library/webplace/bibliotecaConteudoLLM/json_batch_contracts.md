# JSON batch contracts (hints for /ask)

## Address-like rows

Prefer one object per line or a fixed `segmentos` array length as specified by the client.

Suggested field semantics when the prompt uses `logradouro` + `nome`:

- `logradouro`: abbreviation or full type only — RUA, AVENIDA, AV, ALAMEDA, TRAVESSA, EST, ESTRADA, PRACA, VILA, etc.
- `nome`: street name without type and without building number.
- `numero`: house/building number only.
- `bairro`: neighborhood; normalize case as requested (e.g. `VILA NOVA CURUÇA`).

## Forbidden in JSON field values

Do **not** write `<NAME>`, `<...>`, or any placeholder. Use literals taken from the input address string for that segment. Example for input `Av Jose Muniz Ribeiro,255,Vila Paranaguá`:

- `logradouro`: `AV` (or `AVENIDA` if the prompt asks for full words)
- `nome`: `JOSE MUNIZ RIBEIRO` (or preserve casing if the prompt says so)
- `bairro`: `VILA PARANAGUÁ` (or as requested)

Wrong: `"nome": "<NAME> RIBEIRO"`. Right: actual tokens from the source text.

## Validity

The response must parse as JSON. Arrays use `[` `]`. No trailing commentary outside the root object.
