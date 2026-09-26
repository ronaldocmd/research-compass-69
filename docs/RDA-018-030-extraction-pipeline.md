# RDA-018 a RDA-030 — Pipeline de Extração (Sprint 3)

Pipeline que transforma um `Document` baixado em `Claim`s com evidência,
score de confiança, validação e cadeia de proveniência completa.

## Fluxo de dados

```
Document (PENDING)
  -> Downloader            (RDA-018) -> bytes brutos
  -> PDFExtractor           (RDA-020/021) -> texto / estrutura
  -> DocumentChunker        (RDA-022) -> Chunk[]
  -> EmbeddingService       (RDA-023) -> EmbeddingResult[]  (persistido em `chunks`)
  -> DocumentRetriever      (RDA-024) -> RetrievedChunk[]   (similaridade coseno em memória)
  -> ClaimExtractor         (RDA-025) -> Claim[]            (via LLM)
  -> EvidenceExtractor      (RDA-026) -> Evidence[]         (via LLM)
  -> ConfidenceScorer       (RDA-027) -> ScoredClaim        (determinístico, sem LLM)
  -> EvidenceValidator      (RDA-028) -> ValidationResult   (via LLM)
  -> ProvenanceResolver     (RDA-029) -> ProvenanceChain
```

Nenhum destes módulos expõe endpoints HTTP próprios — são consumidos
internamente pelos nodes de orquestração (ver
`RDA-031-037-orchestration.md`).

## Download (RDA-018)

`backend/app/services/downloader/downloader.py::DocumentDownloader` — usa
`httpx.Client` síncrono (injetável, testado com `MockTransport`); valida
timeout, `max_size` e `content-type` permitido (`settings.DOWNLOAD_*`).

- DTO: `DownloadResult{content, content_type, size, downloaded_at, source_url}`
- Exceções: `DownloadError`, `DownloadHTTPError`, `DownloadTimeoutError`,
  `FileTooLargeError`, `InvalidContentTypeError`

## Extração de PDF (RDA-020/021)

`backend/app/services/extraction/pdf_extractor.py::PDFExtractor` (usa `pypdf`):

- `extract()` → `ExtractionResult` com `ExtractedPage{page_number, text, char_count}` (texto simples).
- `extract_structured()` → `StructuredExtractionResult` com `StructuredPage`
  contendo `DocumentElement{type: heading|paragraph|table, level, text, page_number, position}`.
  Heurística por tamanho de fonte (`_HEADING_FONT_RATIO=1.15`) e espaçamento
  de colunas (`_TABLE_COLUMN_GAP`) para inferir headings/tabelas.
- Exceções: `PDFNotFoundError`, `CorruptedPDFError`.

## Chunking (RDA-022)

`backend/app/services/chunking/chunker.py::DocumentChunker(chunk_size=settings.CHUNK_SIZE_CHARS, strategy=StructureAwareChunkingStrategy())`

- `chunk_id` determinístico via `uuid5` (namespace fixo `_CHUNK_ID_NAMESPACE`):
  mesmo documento + mesma config sempre geram os mesmos IDs.
- DTOs: `Chunk{chunk_id, document_id, text, page_number, section, index, char_count}`, `ChunkingResult`.
- Estratégias em `strategies.py` (`ChunkingStrategy` ABC + `StructureAwareChunkingStrategy`).

Persistência: model `backend/app/models/chunk.py`, tabela `chunks`.

## Embeddings (RDA-023)

`backend/app/services/embeddings/embedding_service.py::EmbeddingService` orquestra um
`EmbeddingProvider` abstrato (implementação `OpenAIEmbeddingProvider`), em batches
(`settings.EMBEDDING_BATCH_SIZE`). Isola falhas por chunk: uma falha não derruba o
lote inteiro — cada chunk sempre recebe um `EmbeddingResult{chunk_id, embedding,
model, dimension, embedded_at, success, error}`.

## Retrieval (RDA-024)

`backend/app/services/retrieval/retriever.py::DocumentRetriever` — índice em
memória (MVP, sem pgvector) de `IndexedChunk` (chunk + embedding + título do
doc). `cosine_similarity()` puro em Python (sem numpy); vetores de tamanhos
diferentes ou norma zero tratados como similaridade 0. Retorna
`RetrievedChunk{..., score}`, top-K acima de `min_score`.

## Extração de claims (RDA-025)

`backend/app/services/claims/extractor.py` — LLM extrai
`Claim{claim_id, text, chunk_ids, document_id, page_number, extracted_at}`.
`chunk_ids` nunca vazio; `document_id`/`page_number` sempre derivados do
primeiro chunk fonte (nunca confiados diretamente ao LLM).

## Extração de evidências (RDA-026)

`backend/app/services/evidence/extractor.py` — `EvidenceStatus`
(SUPPORTED/UNSUPPORTED/INCONCLUSIVE). `EvidenceDraft` (saída bruta do LLM) é
convertido em `Evidence` validado; `text` só é populado quando efetivamente
ancorado no chunk fonte (nunca inventado pelo modelo).

## Confidence scoring (RDA-027)

`backend/app/services/confidence/scorer.py::ConfidenceScorer.score(claim, evidence, retrieval_scores=None)`
— **100% determinístico** (sem LLM), regras em `confidence/rules.py`
(`base_score`, `coverage_bonus`, `retrieval_bonus`, `classify_level`).
Saída: `ConfidenceScore{level: HIGH|MEDIUM|LOW, score (0-1), reasoning, factors}`,
combinada em `ScoredClaim{claim, evidence, confidence, scored_at}`.

## Validação de evidências (RDA-028)

`backend/app/services/validation/validator.py` — LLM classifica cada par
claim/evidence como `SUPPORTED`/`PARTIALLY_SUPPORTED`/`UNSUPPORTED`
(`ValidationStatus`), gerando
`ValidationResult{validation_id, claim_id, evidence_id, status, reasoning, validated_at, model_used}`.

## Provenance (RDA-029)

`backend/app/services/provenance/resolver.py` — monta
`ProvenanceChain{claim_id, chain: list[ProvenanceLink], resolved_at, is_complete}`
com níveis **claim → evidence → chunk → page → document → source**, onde
`DocumentSource{document_id, title, url, doi, page_number, chunk_id}`.

## Migrations

| Revisão                      | Descrição                          |
| ------------------------------ | ----------------------------------- |
| `72dcaf428a7f` / `b5657d4a7b59` | Criação da tabela `chunks`          |
| `8acf69d2ca8e` / `c4544f4654ee` | Adiciona coluna de embedding a `chunks` |

> Há duas revisões para "criar `chunks`" e duas para "adicionar embeddings" —
> aparente branch/merge no histórico de migrations do Alembic. Ambos os pares
> aplicam corretamente em sequência (`alembic upgrade head` roda sem
> conflito), mas vale investigar se uma delas é redundante antes de novas
> migrations na tabela `chunks`.

## Testes

`backend/tests/`: `test_document_downloader.py`, `test_document_chunker.py`,
`test_embedding_service.py`, `test_claim_extractor.py`, `test_evidence_extractor.py`,
`test_evidence_validator.py`, `test_confidence.py`, `test_deduplicator.py`, entre outros.
