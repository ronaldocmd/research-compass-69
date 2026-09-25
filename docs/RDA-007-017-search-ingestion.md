# RDA-007 a RDA-017 — Busca e Ingestão de Documentos (Sprint 2)

Arquitetura de busca em múltiplas fontes acadêmicas, normalização/deduplicação de
resultados e persistência de `Document`, mantendo a mesma separação em camadas do
RDA-006 (**API → Service → Repository → Database**).

## Busca (`backend/app/services/search/`)

| Arquivo             | Responsabilidade                                                        |
| -------------------- | ------------------------------------------------------------------------ |
| `provider.py`        | `SearchProvider` (ABC): contrato único `search(query, options) -> list[NormalizedSearchResult]` |
| `openalex.py`        | `OpenAlexSearchProvider` (RDA-012)                                       |
| `crossref.py`        | `CrossrefSearchProvider` (RDA-013)                                       |
| `normalizer.py`      | Normalização pura dos resultados (RDA-015)                               |
| `deduplicator.py`    | `SearchDeduplicator`, estratégia hierárquica (RDA-016)                   |
| `search_service.py`  | `SearchService`, orquestra os providers registrados (RDA-014)            |
| `exceptions.py`      | `SearchProviderError`, `UnknownSearchProviderError`                      |

Cada provider adapta a resposta da sua API nativa para `NormalizedSearchResult`
(DTO em `app/schemas/search.py`), de forma que o `SearchService` nunca fale
diretamente com uma API externa — apenas com providers registrados
(`{"openalex": OpenAlexSearchProvider, "crossref": CrossrefSearchProvider}`).

### Normalização (RDA-015)

- `title`, `abstract`, `doi`, `url`: viram `None` quando ausentes/inválidos
  (nunca string vazia).
- `authors`: normaliza para `[]` quando ausente.
- `publication_year`: validado no range 1000–2100.
- `doi`: validado por regex `^10\.\d{4,9}/\S+$`; o valor bruto original é
  preservado em `metadata["raw_doi"]` (idem para `raw_url`).

### Deduplicação (RDA-016)

Estratégia hierárquica, na ordem: **DOI → external_id → URL normalizada →
hash de conteúdo** (título normalizado + primeiro autor + ano).
`DEFAULT_PROVIDER_PREFERENCE = ["openalex", "crossref"]` decide qual registro
"vence" ao mesclar metadados de duplicatas encontradas em providers diferentes.

## Persistência de `Document` (RDA-017)

| Camada     | Arquivo                                              |
| ---------- | ----------------------------------------------------- |
| Model      | `backend/app/models/document.py` (tabela `documents`) |
| Repository | `backend/app/repositories/document_repository.py`     |

Campos principais: `id` (UUID), `research_id` (FK `researches.id`, CASCADE),
`source`, `external_id`, `title`, `authors` (JSON/JSONB), `publication_year`,
`doi`, `url`, `abstract`, `document_metadata` (JSON/JSONB), `status`
(`DocumentStatus`: PENDING/DOWNLOADED/PROCESSED/FAILED), `relevance_score`,
`file_hash`, `storage_path`, `file_size`, `created_at`/`updated_at`.

`DocumentRepository` segue o mesmo padrão do `ResearchRepository` (RDA-006):
`create`, `bulk_create`, `get_by_id`, `get_by_research_id(skip, limit)`
(ordenado por `created_at DESC`), `update`, `delete`.

> **Sem endpoints HTTP dedicados a `documents`.** Diferente de `Research`
> (RDA-006), `Document` não é exposto via REST direto nesta fase — é
> consumido internamente pelo pipeline de orquestração (ver
> `RDA-031-037-orchestration.md`).

## Migrations

| Revisão                                  | Descrição                          |
| ----------------------------------------- | ----------------------------------- |
| `20260818_0003_documents`                 | Cria tabela `documents`             |
| `20260818_0004_document_storage`          | Adiciona colunas de storage (`storage_path`, `file_hash`, `file_size`) |

## Testes

Cobertura em `backend/tests/` inclui, entre outros: `test_crossref_search_provider.py`,
`test_deduplicator.py`, `test_document_repository.py`, `test_document_service.py`.
