# RDA-063 — Grounding Determinístico + Validação Híbrida

**Data:** 2026-08-28
**Commit base:** `0547113` (RDA-062)
**Ambiente:** backend FastAPI/SQLAlchemy; LLM OpenAI `gpt-4o-mini` via proxy litellm; frontend Next.js.

---

## 1. VEREDITO

**ACEITÁVEL.**

O RDA-062 deixou a validação semântica dependente de um LLM instável e
não-determinístico. O RDA-063 adiciona uma **camada de grounding determinística**
que verifica fatos objetivamente verificáveis (o texto da evidence está no
chunk? os números do claim batem com a fonte? o claim inverte a negação da
fonte?) **antes** de confiar em qualquer julgamento semântico do LLM. Um teste
determinístico que falha **não é anulado** por uma resposta positiva do LLM.

O grounding é conservador por projeto: "não encontrado textualmente" **não** é
tratado como "falso" (normalização, OCR, paráfrase legítima podem esconder uma
passagem real). UNGROUNDED só é retornado quando a evidence está genuinamente
ausente após normalização segura, ou quando um fato verificável é contradito.

---

## 2. TAXONOMIA DE GROUNDING

| Estado | Significado | Efeito na validação |
|---|---|---|
| `GROUNDED` | Evidence presente no chunk (após normalização segura) e fatos verificáveis consistentes | LLM decide |
| `PARTIALLY_GROUNDED` | Parte da evidence/claim está grounded, mas não tudo (claim composto, número alterado, negação invertida) | Cap em `PARTIALLY_SUPPORTED`; negação invertida → `CONTRADICTED` |
| `UNGROUNDED` | Evidence ausente do chunk, ou fato verificável contradito | `UNSUPPORTED` (impossível SUPPORTED) |
| `UNVERIFIABLE` | Sem chunk disponível para verificar | Cap em `PARTIALLY_SUPPORTED` (nunca HIGH) |

---

## 3. NORMALIZAÇÃO SEGURA

Aplicadas (preservam significado):
- Unicode NFKC (liga, dígitos full-width, aspas curvas → canônicas).
- Colapso de whitespace (espaços, tabs, newlines → espaço único).
- Case folding para comparação.
- Remoção de pontuação nas bordas.

**Não** aplicadas (removeriam significado):
- Remoção de dígitos/tokens numéricos.
- Remoção de palavras de negação (no, not, não, sem, ...).
- Stemming/lemmatização (agressivo demais para grounding).

---

## 4. DETECÇÃO DE NÚMEROS

Detecta alterações objetivas de números que o LLM pode perder:

| Claim | Fonte | Resultado |
|---|---|---|
| 12% | 12% | GROUNDED |
| 21% | 12% | PARTIALLY_GROUNDED (mismatch 21%) |
| 12% | 12.0% | GROUNDED (formas equivalentes) |
| 2024 | 2023 | PARTIALLY_GROUNDED (mismatch 2024) |
| 5 | 5.0 | GROUNDED (equivalentes) |

Limites documentados: formas equivalentes (1.2 billion vs 1,200 million) **não**
são resolvidas — são tokens diferentes e seriam sinalizadas. Isso é
conservador e aceitável; o validator semântico pode reconciliar.

---

## 5. DETECÇÃO DE NEGAÇÃO

Detecta inversões explícitas de negação:

| Claim | Fonte | Resultado |
|---|---|---|
| "found a significant effect" | "found no significant effect" | PARTIALLY_GROUNDED (flip) |
| "found a significant effect" | "found a significant effect" | GROUNDED |
| "encontrou um efeito significativo" | "não encontrou efeito significativo" | PARTIALLY_GROUNDED (flip) |

Limites documentados: negação é sensível a contexto; uma lista de palavras não
resolve todos os casos. Antônimos lexicais (profit vs loss) **não** são
detectados como negação — o validator semântico os trata. Quando ambíguo, o
detector retorna False (sem flip) e o LLM decide.

---

## 6. GROUNDING PARCIAL

Um claim composto não deve ser tratado como totalmente grounded por uma
passagem que cobre apenas parte dele:

| Claim | Fonte | Resultado |
|---|---|---|
| "X increased by 12% in 2022" | "X increased by 12% in 2022" | GROUNDED |
| "X increased by 12% in 2022 and caused Y to increase" | "X increased by 12% in 2022" | PARTIALLY_GROUNDED |
| "X increased by 12% and Y decreased by 8%" | "X increased by 12%" | PARTIALLY_GROUNDED |

Regra: cobertura de tokens de conteúdo < 0.6 **ou** ≥ 2 tokens de conteúdo
ausentes do chunk → PARTIALLY_GROUNDED.

---

## 7. INTEGRIDADE (HASH)

Cada `GroundingResult` registra o **SHA-256 do texto do chunk** no momento do
grounding (`content_hash`). Isso permite que a cadeia de provenance detecte
adulteração posterior do conteúdo da fonte.

---

## 8. ARQUITETURA HÍBRIDA

```
Claim + RetrievedChunks
  → EvidenceExtractor (LLM): evidence text + chunk_id + status
  → validation_node:
      → GROUNDING (determinístico): evidence ∈ chunk? números? negação?
          → UNGROUNDED → UNSUPPORTED (override do LLM)
          → PARTIALLY_GROUNDED → PARTIALLY_SUPPORTED / CONTRADICTED
          → UNVERIFIABLE → PARTIALLY_SUPPORTED
          → GROUNDED → LLM decide
      → ConfidenceScorer (determinístico): base + retrieval + coverage,
          com gate de grounding (UNGROUNDED → LOW, PARTIAL/UNVERIFIABLE → MEDIUM)
      → ProvenanceResolver
      → EvidenceValidator (LLM): julgamento semântico
  → synthesis_node: exige ≥1 validação SUPPORTED
```

**Princípio central:** um teste determinístico que falha **não é anulado** por
uma resposta positiva do LLM. O grounding roda **antes** do validator semântico
e o override é aplicado ao resultado final.

---

## 9. ESTADOS DE VALIDAÇÃO

Adicionado `CONTRADICTED` ao `ValidationStatus` (distinto de `UNSUPPORTED`):

- `CONTRADICTED`: o claim **inverte** a negação da fonte (contradição direta).
- `UNSUPPORTED`: a evidence não suporta o claim (ausência de suporte, não
  contradição).

O `_grounding_override` mapeia: negação invertida → `CONTRADICTED`; evidence
ausente → `UNSUPPORTED`. O filtro de síntese exige `SUPPORTED`, então claims
contraditos e não suportados são excluídos do summary.

---

## 10. CONFIDENCE

O `ConfidenceScorer` agora aceita `grounding_results` (opcional, backward
compatible). O gate de grounding:

- Qualquer evidence `UNGROUNDED` → **LOW** (impossível HIGH, mesmo com
  retrieval alto e status SUPPORTED do extractor).
- `PARTIALLY_GROUNDED` ou `UNVERIFIABLE` → cap em **MEDIUM**.
- `GROUNDED` → score normal.

Isso impede que a **similaridade de retrieval** infle a confidence para
evidence que não está realmente grounded na fonte.

---

## 11. PERSISTÊNCIA E RESTART

Nova tabela `groundings` (migração `0007_grounding`) persiste cada
`GroundingResult` com UUID estável. A API `/evidence` expõe `groundings` na
cadeia. O teste E2E `test_run_persists_documents_chunks_and_summary` verifica
que o grounding é persistido e recuperável via API após o run (sobrevive a
restart).

---

## 12. BENCHMARK DE GROUNDING

Benchmark `grounding_rda063_v1.json` (35 casos, 7 categorias × 5).

| Categoria | Acertos | Accuracy |
|---|---|---|
| supported | 5/5 | 1.00 |
| number | 5/5 | 1.00 |
| negation | 4/5 | 0.80 |
| fabricated | 5/5 | 1.00 |
| wrong_chunk | 5/5 | 1.00 |
| partial | 5/5 | 1.00 |
| unverifiable | 5/5 | 1.00 |
| **Total** | **34/35** | **0.971** |

Único miss: `NG03` (profit vs loss) — antônimo lexical, não negação explícita.
Limitação documentada; o validator semântico trata.

---

## 13. RED TEAM APÓS IMPLEMENTAÇÃO

O grounding gate bloqueia deterministicamente os ataques críticos do RDA-062:

| Ataque | Antes (RDA-062) | Depois (RDA-063) |
|---|---|---|
| Evidence fabricada | SUPPORTED → HIGH → summary | **UNGROUNDED → UNSUPPORTED** |
| Chunk errado | SUPPORTED → HIGH → summary | **UNGROUNDED → UNSUPPORTED** |
| Número alterado (12%→21%) | SUPPORTED → HIGH → summary | **PARTIALLY_GROUNDED → PARTIALLY_SUPPORTED** |
| Negação invertida | SUPPORTED → HIGH → summary | **PARTIALLY_GROUNDED → CONTRADICTED** |
| Claim composto parcial | SUPPORTED → HIGH → summary | **PARTIALLY_GROUNDED → PARTIALLY_SUPPORTED** |

Teste de regressão LLM (ao vivo): para evidence fabricada, mesmo que o LLM
diga `SUPPORTED`, o grounding retorna `UNGROUNDED` e o override força
`UNSUPPORTED`. **O teste determinístico não é anulado pelo LLM.**

---

## 14. ALTERAÇÕES

| Arquivo | Mudança |
|---|---|
| `backend/app/services/grounding/` (novo) | Módulo de grounding: `schemas.py`, `normalize.py`, `numbers.py`, `negation.py`, `grounder.py` |
| `backend/app/services/orchestration/nodes.py` | `validation_node` computa grounding e aplica override; `_grounding_override` |
| `backend/app/services/confidence/scorer.py` | Gate de grounding no score (UNGROUNDED→LOW, PARTIAL/UNVERIFIABLE→MEDIUM) |
| `backend/app/services/validation/schemas.py` | Adicionado `CONTRADICTED` |
| `backend/app/services/workflow/state.py` | Campo `grounding_results` |
| `backend/app/models/evidence_chain.py` | Modelo `GroundingRecord` |
| `backend/app/repositories/evidence_chain_repository.py` | Persistência e leitura de groundings |
| `backend/app/schemas/evidence.py` | `GroundingResponse` + campo `groundings` |
| `backend/app/api/v1/endpoints/evidence.py` | Expõe `groundings` na API |
| `backend/alembic/versions/20260828_0007_grounding.py` | Migração: tabela `groundings` + enum `contradicted` |
| `backend/app/evaluation/grounding_benchmark.py` | Módulo de avaliação do grounding |
| `backend/data/benchmarks/grounding_rda063_v1.json` | Benchmark de 35 casos |
| `backend/data/evaluation/grounding_rda063_*.json` | Relatório do benchmark |
| `backend/tests/test_grounding.py` | Testes do grounding |
| `backend/tests/test_grounding_benchmark.py` | Testes do benchmark |
| `backend/tests/test_nodes.py` | Testes do gate no validation_node |
| `backend/tests/test_confidence.py` | Testes do gate no confidence |
| `backend/tests/test_workflow_integration.py` | E2E: persistência de grounding |
| `backend/tests/test_db_connection.py` | Tabela `groundings` no metadata |

---

## 15. TESTES

```
Backend:  522 passed, 16 skipped (baseline 497; +25 novos)
Frontend: 34 passed (vitest); nenhum arquivo de frontend alterado
RDA-062:  test_redteam.py + test_nodes.py — passam
RDA-063:  test_grounding.py (13), test_grounding_benchmark.py (3),
          test_nodes.py (4 gate), test_confidence.py (5 gate),
          test_workflow_integration.py (E2E persistência) — passam
E2E:      test_workflow_integration.py (run real com fakes) — passa
```

---

## 16. PROBLEMAS REMANESCENTES

| Gravidade | Problema |
|---|---|
| **MÉDIO** | Antônimos lexicais (profit vs loss) não são detectados como negação; o validator semântico os trata. |
| **MÉDIO** | Formas numéricas equivalentes (1.2 billion vs 1,200 million) são sinalizadas como mismatch (conservador). |
| **MÉDIO** | Instabilidade do provedor LLM persiste; o fallback conservador (UNSUPPORTED) reduz a cobertura de validação semântica. |
| **BAIXO** | A detecção de negação é baseada em lista de palavras; casos ambíguos ("not only") podem gerar falso flip. |

---

## 17. MAIOR RISCO SEGUINTE

O grounding determinístico agora protege contra os false positives mais
críticos (fabricada, chunk errado, número alterado, negação). O maior risco
remanescente é a **validação semântica ainda depender de um LLM instável** para
casos que o grounding não cobre (causalidade, generalização, antônimos). O
próximo passo de maior valor é **tornar a validação semântica mais robusta**
(ex.: instruções explícitas para distinguir associação de causalidade e
rejeitar evidence não verificável) e **estabilizar o provedor LLM** (retry com
backoff, fallback de modelo).
