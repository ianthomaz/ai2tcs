# Features (serviços satélite)

Componentes **opcionais** ou **à parte** do motor principal da API LLM em [`../llm_api/`](../llm_api/).

| Pasta | Descrição |
|--------|-----------|
| [`ExtratNFdata/`](ExtratNFdata/) | Serviço auxiliar de extração fiscal (código próprio). O endpoint público **`POST /nfExtract`** da API principal está documentado em [`docs/refs/ManualNF_Extract`](../docs/refs/ManualNF_Extract). |

Contratos HTTP (`/ask`, `/nfExtract`, auth, corpos) **não** dependem destes caminhos no disco — só da URL da API e variáveis de ambiente nos clientes.
