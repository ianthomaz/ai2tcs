# RAG × portas — corpus coerente

Índice único: `bikeanjoall_2026` ← `bibliotecaConteudoLLM/` + `mapaFluxosLLM/`.

| Arquivo | Função |
|---|---|
| [`corpus-manifest.json`](corpus-manifest.json) | inventário: role, canais, prioridade, tópicos |
| [`retrieval-hints.json`](retrieval-hints.json) | boost/downrank por porta + `intent_clusters` |
| `bibliotecaConteudoLLM/35_rag_prioridades_por_pergunta.md` | mapa **dentro** do índice (a LLM lê) |
| `bibliotecaConteudoLLM/34_suporte_chamados_rascunho.md` | fatos/proibições do canal chamado |
| `bibliotecaConteudoLLM/27_…` + `mapaFluxosLLM/06–09` | operação 2026 sem stubs vazios |

---

## Quem usa RAG

| Porta | RAG | Direção |
|---|---|---|
| `/ask` | sim | boost Zap (24/31/32/33/16/23 + mapas CEP/router); downrank estatuto/regimento/INDEX |
| `/feedbackTriage` | **não** | few-shots |
| `/healthNormalize` | **não** | allowlist + `health-normalize-v1.md` + `health-normalize-fewshots.md` |
| `/replySuggest` | sim | boost `34`/`35`/FAQ/contato; **downrank** `mapaFluxosLLM` e identidade do bot. A UI de `/admin/suporte` não lista as fontes. |

**Nunca** ingerir feedback, saúde ou texto de chamado.

### Por que saúde não tem RAG

O índice `bikeanjoall_2026` é conteúdo institucional/ops. Texto de saúde de pessoa é
dado sensível e **fora** do ingest. A memória da porta é: allowlist + prompt + few-shots
+ pós-processo no BA. Melhorar “RAG de saúde” = melhorar **esse pacote** e o
`health-normalize.eval.jsonl` — não acrescentar MD na biblioteca.

---

## Convenção de arquivo (obrigatória neste repo)

1. Todo `.md` do corpus começa com `# Sobre: …` — o ingest do ai2tcs usa o H1
   para título/keywords do primeiro chunk.
2. Seções longas com `##` — o chunker parte por heading.
3. Sem links para `docs/`, `zapzap/` ou paths fora do corpus (a LLM não anexa).
4. Papel de cada arquivo declarado no `corpus-manifest.json`.

Teste: `ai2tcs-contracts.test.ts` (manifest completo + Sobre + hints).

---

## No ai2tcs (handler)

```text
chunks = retrieve(project, query, top_k=max)
chunks = apply_port_boost(chunks, retrieval-hints.ports[port])
if port == ask:
  chunks = apply_intent_cluster(chunks, query, retrieval-hints.intent_clusters)
return chunks[:top_k_suggest]
```

`apply_*`: se `path` contém substring de boost, reduzir distância (ex. −0.05);
downrank: +0.08; `legal_downrank` só sobe no cluster `governanca_legal`.

---

## Re-ingest

Depois do commit neste repo, no mini62:

```bash
cd ~/Documents/Projects/BikeAnjo_Sistema2026 && git pull --ff-only
./tools/scripts/llm-ingest-bikeanjo.sh ignore/zapzap.env.prod
```

Sem re-ingest, `34`/`35` e stubs novos **não** entram no Chroma.
