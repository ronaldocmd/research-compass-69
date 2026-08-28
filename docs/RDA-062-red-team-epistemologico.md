# RDA-062 — Red Team Epistemológico + Auditoria dos Quality Gates

**Data:** 2026-08-28
**Commit base:** `ebff94b` (RDA-061)
**Ambiente:** backend FastAPI/SQLAlchemy; LLM OpenAI `gpt-4o-mini` via proxy litellm; frontend Next.js.

---

## 1. VEREDITO

**ACEITÁVEL** (com ressalvas).

O RDA-061 **não** é plenamente robusto. O red team provou que a cadeia
epistemológica tinha um **defeito crítico de false positive**: claims
unsupported (causalidade, generalização, evidence fabricada, chunk errado)
chegavam ao summary como se fossem suportados. A correção implementada
(portão de validação no synthesis) elimina esses false positives no nível da
decisão, mas o sistema ainda depende de LLM para a validação semântica e
apresenta instabilidade do provedor LLM. Não declaro o sistema "plenamente
robusto"; as lacunas remanescentes estão listadas na seção 13.

---

## 2. RED TEAM SCORE

**Ataques resistidos / ataques totais** (benchmark de decisão, 50 casos):

- Baseline (sem correção): **30/50** (60%)
- Com portão de validação: **50/50** (100%)

Ataques LLM ao vivo (validator/extractor): os ataques de **número alterado**,
**negação**, **contradição** e **evidence sem relação** foram resistidos; os
ataques de **causalidade**, **generalização** e **evidence fabricada** foram
perdidos (ver seção 3).

---

## 3. MATRIZ DE ATAQUES

| Ataque | Resultado esperado | Resultado real (baseline) | Passou? | Gravidade |
|---|---|---|---|---|
| 1. Evidence sem relação | UNSUPPORTED | UNSUPPORTED | Sim | — |
| 2. Claim mais forte (causalidade) | UNSUPPORTED | PARTIALLY_SUPPORTED / inconclusive → MEDIUM → summary | **Não** | **CRÍTICO** |
| 3. Generalização geográfica | UNSUPPORTED | PARTIALLY_SUPPORTED / inconclusive → MEDIUM → summary | **Não** | **CRÍTICO** |
| 4. Generalização temporal | UNSUPPORTED | PARTIALLY_SUPPORTED → MEDIUM → summary | **Não** | **CRÍTICO** |
| 5. Número alterado | UNSUPPORTED | UNSUPPORTED | Sim | — |
| 6. Negação | UNSUPPORTED | UNSUPPORTED | Sim | — |
| 7. Documento errado | INVALID | UNSUPPORTED (excluído) | Sim | — |
| 8. Chunk errado | INVALID | SUPPORTED → HIGH → summary | **Não** | **CRÍTICO** |
| 9. Evidence fabricada | INVALID | SUPPORTED → HIGH → summary | **Não** | **CRÍTICO** |
| 10. Evidence parcial (suportada) | SUPPORTED | SUPPORTED | Sim | — |
| 10b. Evidence parcial (overstatement) | UNSUPPORTED | PARTIALLY_SUPPORTED | **Não** | ALTO |
| 11. Contradição entre fontes | detectar conflito | conflito ignorado no score (HIGH) | **Não** | ALTO |
| 12. Retrieval alto ≠ evidence | não inflar | retrieval infla confidence | **Não** | ALTO |
| 13. Evidence semelhante mas contraditória | UNSUPPORTED | UNSUPPORTED | Sim | — |
| 14. Múltiplas evidences | combinar | avaliadas isoladamente | Parcial | MÉDIO |
| 15. Conflito entre evidences | reduzir/qualificar | conflito ignorado | **Não** | ALTO |
| 16. Provenance | UNVERIFIABLE | cadeia resolvida, mas não verifica texto | Parcial | MÉDIO |
| 17. Restart | preservar | persistido em DB, recuperável via API | Sim | — |
| 18. Summary | excluir unsupported | **incluía unsupported** (baseline) | **Não** | **CRÍTICO** |

---

## 4. FALSE POSITIVES

Medidos no benchmark de decisão (50 casos), baseline:

- **unsupported → supported**: 20 casos (FPR = 0.444). Categorias que falharam
  por completo (0/5): **causalidade**, **generalização**, **evidence
  fabricada**, **chunk errado**.
- **fabricated evidence → valid**: 5/5 (A9) — o validator LLM aceitou evidence
  plausível e fabricada como `supported`.
- **contradicted → supported**: o `ConfidenceScorer` ignora contradição
  (1 supported + 1 unsupported → HIGH 0.8).
- **causalidade → supported**: associação tratada como suporte parcial e
  elevada a MEDIUM → summary.

Após a correção (portão de validação): **0 false positives** (FPR = 0.0).

---

## 5. FALSE NEGATIVES

- **supported → unsupported**: 0 no benchmark (recall = 1.0). Nenhum claim
  genuinamente suportado foi excluído.
- A correção é conservadora por projeto: quando o validator LLM falha, o claim
  é tratado como UNSUPPORTED (preferindo rejeitar um claim verdadeiro a aceitar
  um não verificado). Isso pode gerar false negatives sob instabilidade do LLM,
  mas é o comportamento desejado pelo princípio do ticket.

---

## 6. CONFIDENCE

O `ConfidenceScorer` é **determinístico** e **não infla com quantidade**, mas
**confunde similarity com support** e **ignora contradições**.

Exemplos de scores (retrieval 0.9):

| Caso | Score | Nível |
|---|---|---|
| 1 evidence suportada | 0.8 | HIGH |
| 5 evidences inconclusive | 0.7 | MEDIUM |
| 1 evidence unsupported | 0.2 | LOW |
| 10 evidences unsupported | 0.2 | LOW |
| 1 supported + 1 unsupported (conflito) | 0.8 | HIGH |

Problemas comprovados:
- **Retrieval bonus**: 1 evidence suportada (0.6) + retrieval alto (0.2) = 0.8
  → HIGH. Similarity de retrieval infla o score.
- **Contradição ignorada**: o score usa `strongest_status` e ignora evidence
  contraditória (caso E → HIGH).
- **Validation não influencia o score**: o score deriva do status do extractor,
  não da validação independente. (Corrigido no nível do summary, não do score.)

---

## 7. PROVENANCE

A cadeia é **persistida e auditável** (tabelas `claims`, `evidence`,
`validations`, `provenance`, `confidence`), com UUIDs estáveis e idempotência.
A API `/evidence` recupera a cadeia completa após restart.

**Lacuna**: o `ProvenanceResolver` monta a cadeia claim → evidence → chunk →
document → source, mas **não verifica deterministicamente** que o texto da
evidence aparece no chunk. A verificação de grounding existe no
`EvidenceExtractor` (`is_text_grounded`), mas a provenance em si não revalida o
texto. Gravidade MÉDIA.

---

## 8. SUMMARY

**Antes da correção**: o summary incluía claims unsupported (causalidade,
generalização, fabricada, chunk errado) porque o filtro usava apenas o
confidence, que era inflado por retrieval/similarity.

**Após a correção**: o `_supported_claims` exige que o claim tenha **pelo menos
uma validação SUPPORTED** para entrar no summary. Claims contraditos,
parciais e não suportados são excluídos. O prompt de síntese agora instrui o
LLM a preservar a qualificação de confidence e reportar conflitos
explicitamente.

Quality gates (Fase 28) verificados por teste:
- Caso 1 (0 suportados): sem summary factual. ✓
- Caso 2 (só LOW): sem summary factual. ✓
- Caso 3 (suportados + contraditos): contradito excluído. ✓
- Caso 4 (parciais): parcial excluído. ✓
- Caso 5 (fortemente suportados): summary permitido. ✓

---

## 9. RESTART

A cadeia é persistida no PostgreSQL com UUIDs estáveis e recuperada via API
após restart. O teste `test_run_persists_documents_chunks_and_summary` verifica
que claims, evidence, validations, provenance e confidence são persistidos e
recuperáveis via `GET /research/{id}/evidence`. O resultado da validação
(estado `ValidationRecord.status`) é persistido e não depende de estado em
memória. ✓

---

## 10. BENCHMARK

Benchmark `redteam_rda062_v1.json` (50 casos, 10 categorias × 5).

| Métrica | Baseline | Com portão de validação |
|---|---|---|
| Accuracy | 0.60 | **1.00** |
| Precision | 0.20 | **1.00** |
| Recall | 1.00 | **1.00** |
| False Positive Rate | 0.444 | **0.00** |
| False Negative Rate | 0.00 | **0.00** |

Métrica mais importante — **claims unsupported classificados como SUPPORTED**:
20/45 no baseline → **0/45** após a correção.

---

## 11. ALTERAÇÕES

| Arquivo | Mudança | Motivo | Evidência |
|---|---|---|---|
| `backend/app/services/orchestration/nodes.py` | `_supported_claims` exige ≥1 validação SUPPORTED | Impedir false positives no summary | Benchmark: FPR 0.444 → 0.0 |
| `backend/app/services/orchestration/nodes.py` | `validation_node` registra UNSUPPORTED conservador quando o validator falha | Preferir rejeitar a aceitar não verificado | Instabilidade LLM observada |
| `backend/app/services/orchestration/nodes.py` | Prompt de síntese preserva qualificação e conflitos | Quality gates 3-4 | Fase 22/28 |
| `backend/app/evaluation/redteam.py` | Módulo de avaliação da camada de decisão | Benchmark reproduzível | Fase 25 |
| `backend/data/benchmarks/redteam_rda062_v1.json` | 50 casos adversariais | Benchmark | Fase 25 |
| `backend/data/evaluation/redteam_rda062_*.json` | Relatórios baseline e com correção | Evidência | Fase 26 |
| `backend/tests/test_nodes.py` | Testes do portão de validação + quality gates | Cobertura | Fase 28 |
| `backend/tests/test_redteam.py` | Testes do benchmark | Cobertura | Fase 25 |
| `.gitignore` | Ignora `backend/storage/` | Evitar commit de runtime | — |

---

## 12. TESTES

```
Backend:  497 passed, 16 skipped (baseline 485; +12 novos)
Frontend: 34 passed (vitest); build falha por ambiente pré-existente (ESLint ausente + prerender /404)
RDA-057:  coberto por test_retrieval.py / test_evidence_evaluation.py — passam
RDA-059:  coberto por test_retrieval.py (cross-lingual) — passa
RDA-060:  coberto por test_document_* — passam
RDA-061:  coberto por test_workflow_integration.py / test_nodes.py — passam
RDA-062:  test_redteam.py + test_nodes.py (novos) — passam
E2E:      test_workflow_integration.py (run real com fakes) — passa
```

**Nota frontend**: o build `next build` falha por um problema **pré-existente de
ambiente** (ESLint não instalado + erro de prerender do Next.js em `/404`),
não relacionado a este ticket (nenhum arquivo de frontend foi alterado). Os
testes de frontend passam.

---

## 13. PROBLEMAS REMANESCENTES

| Gravidade | Problema |
|---|---|
| **ALTO** | Validação semântica depende de LLM; o validator aceitou evidence fabricada como `supported` (A9) e não distingue associação de causalidade (A2). |
| **ALTO** | Instabilidade do provedor LLM (proxy litellm → Ollama/OpenRouter) causa `ValidationError`/`EvidenceExtractionError` intermitentes. Mitigado por fallback conservador, mas reduz a cobertura de validação. |
| **MÉDIO** | `ConfidenceScorer` ignora contradições entre evidences (1 supported + 1 unsupported → HIGH). Não afeta o summary (portão de validação), mas o score reportado é enganoso. |
| **MÉDIO** | `ProvenanceResolver` não revalida deterministicamente que o texto da evidence aparece no chunk. |
| **MÉDIO** | Retrieval similarity infla o confidence (bonus de 0.2). |
| **BAIXO** | Observabilidade: falhas de validação registram UNSUPPORTED sem detalhe do erro do provedor. |

---

## 14. MAIOR RISCO SEGUINTE

O maior risco para a confiabilidade científica do RDA agora é a **dependência
da validação semântica em um LLM instável e não-determinístico**. O portão de
validação elimina os false positives *quando* o validator roda, mas:

1. o validator LLM aceitou evidence fabricada como `supported` (A9) e não
   distingue associação de causalidade (A2) — a validação semântica é fraca;
2. quando o provedor LLM falha, o fallback conservador rejeita claims
   verdadeiros (false negatives), reduzindo a utilidade do sistema.

O próximo passo de maior valor é **adicionar verificações determinísticas** à
validação (grounding do texto da evidence no chunk, detecção de negação e de
números alterados) para reduzir a dependência do LLM, e **tornar a validação
semântica mais robusta** (ex.: instruções explícitas para distinguir
associação de causalidade e rejeitar evidence não verificável). Isso ataca
diretamente os dois problemas ALTO remanescentes.
