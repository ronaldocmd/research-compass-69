# RDA-061 — Cadeia Epistemológica: Claim → Evidence → Source → Provenance → Validation

**Data:** 2026-08-27
**Commit base:** `3a7fa8d` (RDA-060)
**Ambiente:** backend FastAPI/SQLAlchemy/PostgreSQL; migração alembic aplicada.

---

## 1. Contexto

O RDA-057 descobriu que `EvidenceExtractor` funciona, mas **claims/evidence não são persistidos**, e que `EvidenceValidator`, `ProvenanceResolver` e `ConfidenceScorer` **não estão conectados** ao workflow. Este ticket audita e implementa a cadeia epistemológica completa, garantindo que toda afirmação produzida pelo RDA possa ser:

1. identificada;
2. ligada a uma ou mais evidências;
3. ligada ao documento de origem;
4. ligada ao trecho específico que a sustenta;
5. rastreada até a origem;
6. validada independentemente;
7. persistida;
8. recuperada após restart;
9. distinguida de afirmações sem suporte.

---

## 2. Auditoria do estado atual

### Cadeia antes do RDA-061

```text
Search → Documents → Chunks → Retrieval → Evidence/Claims → Summary
```

| Requisito | Estado antes | Evidência |
|---|---|---|
| 1. Identificada | Parcial (claim_id existe) | `Claim.claim_id` |
| 2. Ligada a evidências | Sim | `Claim.chunk_ids`, `Evidence.claim_id` |
| 3. Ligada ao documento de origem | Sim | `Claim.document_id`, `Evidence.document_id` |
| 4. Ligada ao trecho específico | Sim | `Claim.chunk_ids`, `Evidence.chunk_id`, `page_number` |
| 5. Rastreada até a origem | **Não** | `ProvenanceResolver` órfão |
| 6. Validada independentemente | **Não** | `EvidenceValidator` órfão |
| 7. Persistida | **Não** | sem tabelas dedicadas |
| 8. Recuperada após restart | **Não** | apenas checkpoint JSON em memória |
| 9. Distinguida de afirmações sem suporte | **Não** | `ConfidenceScorer` órfão; summary usava todas as claims |

### Serviços órfãos (existentes, testados individualmente, não conectados)

- `EvidenceValidator` (`validation/validator.py`) — validação LLM independente de cada evidence.
- `ProvenanceResolver` (`provenance/resolver.py`) — resolve a cadeia claim → evidence → chunk → source.
- `ConfidenceScorer` (`confidence/scorer.py`) — classificação determinística de confiança.

O `evidence_node` conectava apenas retriever → claim_extractor → evidence_extractor e populava `state.claims`/`state.evidence_items`, sem persistência e sem os três serviços.

---

## 3. Solução implementada

### 3.1 Novo nó `validation_node` (entre evidence e synthesis)

`backend/app/services/orchestration/nodes.py`:

- O `evidence_node` agora **registra os chunks recuperados** (`state.retrieved_chunks`, com o score de retrieval) e transiciona para `VALIDATING`.
- O novo `validation_node`:
  - **ConfidenceScorer** — para cada claim, `score_claim(claim, evidence, retrieval_scores)` → `ScoredClaim`.
  - **ProvenanceResolver** — para cada evidence com chunk resolvido, `resolve(claim, evidence, chunk, document_source)` → `ProvenanceChain`.
  - **EvidenceValidator** — para cada evidence, `validate(claim, evidence)` → `ValidationResult` (chamada LLM independente, via `_execute_external` com budget).
  - **Persistência** — quando um persister está conectado, persiste a cadeia antes de transicionar para `SYNTHESIZING`.
- O `synthesis_node` agora **filtra claims por confiança**: apenas claims com nível ≥ `SYNTHESIS_MIN_CONFIDENCE` (default `MEDIUM`) entram no prompt. O prompt anota cada claim com seu nível. Claims sem score são tratadas como sem suporte e excluídas. `state.synthesis_stats` registra `total_claims`/`included`/`excluded_low_confidence`.

### 3.2 Persistência (novas tabelas)

`backend/app/models/evidence_chain.py` — 5 modelos ORM:

| Tabela | Modelo | Chave estável |
|---|---|---|
| `claims` | `ClaimRecord` | `claim_id` |
| `evidence` | `EvidenceRecord` | `evidence_id` |
| `validations` | `ValidationRecord` | `validation_id` |
| `provenance` | `ProvenanceRecord` | `provenance_id` |
| `confidence` | `ConfidenceRecord` | `confidence_id` |

Todas com `research_id` (FK → `researches.id`, `ON DELETE CASCADE`) e índices. Enums nativos PostgreSQL (`evidence_status`, `validation_status`, `confidence_level`).

`backend/app/repositories/evidence_chain_repository.py` — `EvidenceChainRepository.persist(state)` insere a cadeia de forma **idempotente** (pula UUIDs já existentes, para re-execução de checkpoint não duplicar) e expõe leituras por `research_id`.

Migração: `backend/alembic/versions/20260827_0006_evidence_chain.py` (down_revision `e5f0a8d4b6c2`). **Aplicada** ao PostgreSQL de desenvolvimento.

### 3.3 Wiring

`backend/app/services/orchestration/wiring.py`:

- `WorkflowServices` agora instancia `EvidenceValidator`, `ProvenanceResolver`, `ConfidenceScorer` e `EvidenceChainRepository`.
- Novos adapters: `resolve_document_source(document_id, chunk)` (busca o `Document` e monta o `DocumentSource`; retorna `None` se não encontrado) e `persist_evidence_chain(state)`.
- `build_research_nodes` injeta `validator`, `provenance_resolver`, `confidence_scorer`, `document_resolver`, `evidence_persister`.

### 3.4 State

`backend/app/services/workflow/state.py` — novos campos: `retrieved_chunks`, `validation_results`, `provenance_chains`, `scored_claims`, `synthesis_stats`.

### 3.5 Schemas DTO

- `ConfidenceScore` ganhou `confidence_id` (default factory) — para persistência estável.
- `ProvenanceChain` ganhou `provenance_id` (default factory).

### 3.6 API de recuperação

`backend/app/api/v1/endpoints/evidence.py` — `GET /api/v1/researches/{research_id}/evidence` retorna a cadeia completa persistida (`claims`, `evidence`, `validations`, `provenance`, `confidence`). Schemas em `backend/app/schemas/evidence.py`. Registrado no router.

### 3.7 Config

`backend/app/core/config.py` — `SYNTHESIS_MIN_CONFIDENCE: str = "MEDIUM"`.

---

## 4. Verificação

### Testes adicionados/atualizados

- `test_nodes.py`:
  - `test_evidence_node_stores_retrieved_chunks` — chunks registrados com score.
  - `test_validation_node_produces_validation_provenance_confidence` — os 3 serviços conectados.
  - `test_validation_node_skips_when_services_missing` — no-op sem serviços (backwards compatible).
  - `test_validation_node_persists_state` — persister chamado.
  - `test_synthesis_node_filters_low_confidence_claims` — claims LOW excluídas do prompt.
  - `test_synthesis_node_skips_when_no_supported_claims` — sem claims suportadas, sem summary fabricado.
  - `test_evidence_node_produces_claims_and_evidence` — transição agora para `VALIDATING`.
  - `test_synthesis_node_transitions_to_completed` — com `scored_claims`.
- `test_orchestration.py` — `_fake_nodes` e ordem de estágios incluem `validation`.
- `test_workflow_integration.py` — fakes para validator/provenance/confidence; verifica persistência das 5 tabelas e recuperação via API.
- `test_evidence_api.py` (novo) — endpoint vazio para research sem cadeia; 404 para research inexistente.
- `test_db_connection.py` — metadata inclui as 5 novas tabelas.
- `test_health.py` — rota `/evidence` exposta.

### Suítes

- **Backend:** 501 passed, 0 failed.
- **Frontend:** 34 passed.
- **Migração alembic:** `0006_evidence_chain` aplicada ao PostgreSQL (head).

---

## 5. Mapeamento dos 9 requisitos após o RDA-061

| Requisito | Estado após |
|---|---|
| 1. Identificada | `claim_id` estável, persistido |
| 2. Ligada a evidências | `Evidence.claim_id` persistido |
| 3. Ligada ao documento de origem | `claim.document_id`/`evidence.document_id` persistidos |
| 4. Ligada ao trecho específico | `chunk_id`/`page_number` persistidos |
| 5. Rastreada até a origem | `ProvenanceChain` persistido |
| 6. Validada independentemente | `ValidationResult` persistido |
| 7. Persistida | 5 tabelas dedicadas |
| 8. Recuperada após restart | `GET /researches/{id}/evidence` |
| 9. Distinguida de afirmações sem suporte | filtro de confiança no summary + `synthesis_stats` |

---

## 6. Problemas remanescentes

- **MÉDIO — Provenance depende de documento persistido:** se o `document_id` do chunk não existir na tabela `documents` (ex.: documento não persistido), a provenance é pulada (não falha). Em execuções reais o chunk vem do índice de documentos persistidos, então é o caminho normal.
- **BAIXO — Validação LLM é custosa:** cada evidence gera uma chamada LLM independente. O budget guard cobre isso; se o budget estourar, o workflow termina em `BUDGET_EXCEEDED` sem fabricar summary.
- **BAIXO — Frontend não consome a cadeia:** o endpoint existe, mas a UI ainda não exibe a cadeia de evidências (fora do escopo deste ticket).

---

## 7. Artefatos

- `backend/app/models/evidence_chain.py` — 5 modelos ORM.
- `backend/app/repositories/evidence_chain_repository.py` — persistência/leitura da cadeia.
- `backend/alembic/versions/20260827_0006_evidence_chain.py` — migração.
- `backend/app/services/orchestration/nodes.py` — `validation_node` + filtro de síntese.
- `backend/app/services/orchestration/graph.py` — nó `validation` no grafo.
- `backend/app/services/orchestration/wiring.py` — wiring dos serviços órfãos + adapters.
- `backend/app/services/workflow/state.py` — novos campos de estado.
- `backend/app/api/v1/endpoints/evidence.py` + `backend/app/schemas/evidence.py` — API de recuperação.
- `backend/app/core/config.py` — `SYNTHESIS_MIN_CONFIDENCE`.
- Testes: `test_nodes.py`, `test_orchestration.py`, `test_workflow_integration.py`, `test_evidence_api.py`, `test_db_connection.py`, `test_health.py`.
