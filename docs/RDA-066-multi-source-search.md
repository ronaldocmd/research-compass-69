# RDA-066 — Busca em múltiplas fontes

**Data:** 2026-09-26

## 1. Contexto

Até aqui o pipeline consultava só o OpenAlex: `WorkflowServices.search` chamava
`SearchService.search(query)` com o provider padrão, e o `CrossrefSearchProvider` (RDA-013),
embora registrado, nunca era usado. O RDA-060 mostrou que a maioria dos documentos falha no
download (403/paywall, HTML anti-bot) e apontou como mitigação "priorizar fontes OA confiáveis".
Este ticket amplia a cobertura e favorece fontes com PDF aberto.

## 2. Fontes

| Provider (`name`)   | API                                   | Chave           | Observações |
| ------------------- | ------------------------------------- | --------------- | ----------- |
| `openalex`          | OpenAlex Works                        | não             | já existia |
| `crossref`          | Crossref Works                        | não             | já existia; só metadados (raramente PDF) |
| `semantic_scholar`  | Graph API `/paper/search`             | opcional        | usa `openAccessPdf`; **sem chave o limite compartilhado costuma devolver 429** |
| `arxiv`             | `export.arxiv.org/api/query` (Atom)   | não             | sempre com PDF direto; query traduzida para `all:` |
| `europe_pmc`        | `/webservices/rest/search`            | não             | PDF via `fullTextUrlList` ou `PMC…?pdf=render` |
| `core`              | `api.core.ac.uk/v3/search/works`      | **obrigatória** | sem `CORE_API_KEY` o provider não é registrado |

Além disso, o **Unpaywall** (`UnpaywallEnricher`) não é fonte de busca: para resultados com DOI
cuja URL não é um PDF direto, troca a URL pela melhor cópia open access (`url_for_pdf`). Exige
`UNPAYWALL_EMAIL`; sem e-mail é no-op.

## 3. Arquitetura

- `SearchService.search_all(query)` consulta **todos os providers habilitados em paralelo**
  (`ThreadPoolExecutor`), isolando falhas: um provider fora do ar/limitado é logado e ignorado;
  só se **todos** falharem levanta `SearchProviderError` (o run termina FAILED como antes).
- Depois: deduplicação entre fontes (DOI → external_id → URL → hash), enriquecimento Unpaywall e
  intercalação round-robin por fonte, para que a seleção (teto `max_documents`) não seja dominada
  pelo primeiro provider.
- `SearchDeduplicator`: ao mesclar duplicatas, um **link de PDF direto vence uma landing page**,
  mesmo que venha do provider menos preferido. Ordem de preferência: openalex, semantic_scholar,
  europe_pmc, core, arxiv, crossref.
- `search()` (provider único) permanece inalterado.
- Configuração: `SEARCH_PROVIDERS` (lista separada por vírgula), `*_BASE_URL`, `*_TIMEOUT_SECONDS`,
  `SEMANTIC_SCHOLAR_API_KEY`, `CORE_API_KEY`, `UNPAYWALL_EMAIL` (ver `.env.example`).
- Orçamento: cada query continua contando como **1** `search_call` no `BudgetGuard`; a fan-out é interna.

## 4. Tradução de queries

O planner gera queries booleanas. OpenAlex, Crossref, Europe PMC e CORE recebem a query como está;
Semantic Scholar recebe só as palavras-chave (`strip_boolean`); arXiv recebe a sintaxe própria
(`to_arxiv_query`: `"rare earth" AND Brazil` → `all:"rare earth" AND all:Brazil`).

## 5. Segurança

- A resposta do arXiv (XML) é rejeitada se contiver `<!DOCTYPE`/`<!ENTITY` (expansão de entidades).
- Chaves só via variáveis de ambiente; nunca logadas.

## 6. Verificação

- `tests/test_multi_source_search.py`: parsers (respostas simuladas com `httpx.MockTransport`),
  mapeamento de erros (429/HTTP/timeout), dedupe preferindo PDF, `search_all` (paralelismo,
  falha parcial, falha total, intercalação, configuração por env), Unpaywall.
- Consulta real (2026-09-26, query `"rare earth elements" AND recovery`): OpenAlex, arXiv e Europe
  PMC retornaram e parsearam corretamente; Semantic Scholar respondeu 429 sem chave.
  **CORE e Unpaywall não foram exercitados contra a API real** (sem chave/e-mail disponíveis).

## 7. Limitações

- Não resolve paywall de editoras: só aumenta a chance de achar uma cópia aberta.
- Semantic Scholar sem chave é pouco confiável; configure `SEMANTIC_SCHOLAR_API_KEY`.
- Mais fontes = mais resultados por query; o teto `max_documents` (20) na seleção continua valendo.
