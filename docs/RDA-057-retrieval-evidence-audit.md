# RDA-057 — Auditoria Experimental de Retrieval e Evidence

**Data:** 2026-08-27
**Commit base:** `cfa6fc4` (RDA-056)
**Escopo:** medição e diagnóstico — **nenhuma correção de código foi aplicada** neste ticket.
**Ambiente:** embeddings `text-embedding-3-small` (dim 1536) e LLM `gpt-4o-mini` via proxy LiteLLM (`http://localhost:4000/v1`).

---

## 1. Metodologia

### 1.1 Benchmark gold controlado
Criado `backend/data/benchmarks/retrieval_gold_v1.json`: corpus de **24 passagens** sintéticas mas realistas em 6 tópicos do domínio (revisão sistemática, geração de código por LLM, câncer de pulmão, métricas de recomendação, chain-of-thought, embeddings vetoriais) e **14 consultas** com graus de relevância 0–3 definidos pelo conteúdo tópico de cada passagem (não por saída de modelo).

As consultas cobrem dificuldade fácil/média/difícil e os 6 tipos adversariais pedidos: específica, ampla, sinônimo, negativa, ambígua e lexical.

### 1.2 Harness
- `backend/scripts/evaluation/run_retrieval_audit.py` — embute o corpus com o provider real, roda o `DocumentRetriever` real para cada consulta e calcula P@K, R@K, Hit, MRR, NDCG, distribuição de scores, sweep de threshold e sweep de top-k. Grava relatório JSON em `backend/data/evaluation/`.
- `backend/scripts/evaluation/run_evidence_audit.py` — roda o `ClaimExtractor` e o `EvidenceExtractor` reais (LLM) em 4 cenários controlados de suporte/parcial/contradição/ausência, incluindo teste de alucinação.

Reprodutibilidade: cada relatório registra `commit`, `embedding_model`, `llm_model`, parâmetros do retriever e timestamp.

---

## 2. Resultados — Retrieval

### 2.1 Métricas agregadas (config padrão: `top_k=5`, `min_score=0.7`)

| Métrica | Valor |
|---|---|
| P@1 | 0.14 |
| P@5 | 0.03 |
| R@5 | 0.14 |
| Hit@5 | 0.14 |
| MRR | 0.14 |
| NDCG@5 | 0.14 |

**Veredito: recall catastrófico.** Apenas 2 de 14 consultas recuperaram qualquer chunk relevante com a configuração padrão.

### 2.2 Separação de scores (corpus completo, `min_score=0`)

| | Relevantes (28) | Irrelevantes (308) |
|---|---|---|
| média | 0.537 | 0.226 |
| p25 | 0.450 | 0.161 |
| p50 | 0.574 | 0.204 |
| p75 | 0.652 | 0.269 |
| máx | 0.874 | 0.719 |

**Existe separação forte** entre relevantes e irrelevantes, mas o cluster de relevantes termina em p75≈0.65.

### 2.3 Sweep de threshold

| Threshold | P | R | F1 |
|---|---|---|---|
| 0.50 | 0.68 | 0.61 | **0.64** |
| 0.55 | 0.75 | 0.54 | 0.63 |
| 0.60 | 0.77 | 0.36 | 0.49 |
| 0.65 | 0.78 | 0.25 | 0.38 |
| **0.70 (padrão)** | 0.50 | **0.07** | **0.13** |
| 0.75 | 1.00 | 0.04 | 0.07 |

### 2.4 Sweep de top-k (`min_score=0`)

| k | P | R | F1 |
|---|---|---|---|
| 3 | 0.50 | 0.75 | 0.60 |
| 5 | 0.37 | 0.93 | 0.53 |
| 10 | 0.19 | 0.96 | 0.32 |

### 2.5 Diagnóstico de retrieval

O modelo de embedding **rankeia bem** o conteúdo relevante (R@5=0.93 sem threshold), mas o **threshold padrão de 0.7 está acima do cluster de relevantes** (p75≈0.65), filtrando quase tudo e destruindo o recall. O threshold ótimo neste benchmark é **~0.5–0.55** (F1≈0.64). O `RETRIEVAL_MIN_SCORE=0.7` está mal calibrado para a escala de scores deste modelo.

---

## 3. Resultados — Testes adversariais

| Consulta | Tipo | Relevantes recuperados |
|---|---|---|
| q07 (PICO) | específica | ✓ (MRR=1.0) |
| q13 (pass@k) | específica | ✓ (MRR=1.0) |
| q09 (sinônimo) | sinônimo | ✗ (0) |
| q10 (robótica RL) | negativa | ✗ (0, correto) |
| q11 (imagem médica) | ambígua | ✗ (0) |
| q12 (lexical) | lexical | ✗ (0) |

Apenas consultas muito específicas recuperam conteúdo relevante com o threshold padrão. Consultas sinônimas, ambíguas e lexicais falham — consistente com o threshold alto, não necessariamente com o ranking.

---

## 4. Resultados — Document selection (dados reais do RDA-056)

Research `c824ec05` ("Métodos de revisão sistemática"): **35 resultados de busca → 20 selecionados → 2 processados + 8 falhas (HTML) + 25 pendentes.**

Os **2 documentos processados são fora do tópico**:
- "Hunger games search: Visions, conception, implementation..." (algoritmo de otimização metaheurística)
- "Basic concepts and taxonomy of dependable and secure computing" (segurança de computação)

Enquanto o documento **mais relevante** — "Effectiveness and efficiency of search methods in systematic reviews" — **falhou** por ser HTML.

**Diagnóstico:** a seleção de documentos pega os primeiros 20 resultados sem filtro de relevância; o download rejeita HTML (só PDF); o índice acaba poluído com os PDFs que por acaso são baixáveis, que podem ser fora do tópico. Isso **esfomeia a etapa de retrieval** (o índice não contém conteúdo relevante à pergunta).

---

## 5. Resultados — Evidence & Claims (LLM real)

Teste de alucinação controlado (4 cenários):

| Cenário | Esperado | Resultado |
|---|---|---|
| s1 suporte direto | suportado | claim extraído, evidence **SUPPORTED** (verbatim ancorado) ✅ |
| s2 suporte parcial | parcial | **0 claims** (sem alucinação) ✅ |
| s3 contradição | contradição | claim extraído refletindo a fonte (sem efeito), evidence **SUPPORTED** ✅ |
| s4 informação ausente | ausente | **0 claims** (sem alucinação) ✅ |

**Diagnóstico:** a etapa de evidence/claims **não é o gargalo**. O `EvidenceExtractor` ancora a evidence na fonte (`is_text_grounded`: substring ou sobreposição de tokens ≥0.6) e **não inventa** claims quando a informação está ausente. Porém é **esfomeada pelo retrieval**: com 0 chunks relevantes recuperados, produz 0 claims (observado no E2E do RDA-056).

---

## 6. Resultados — Provenance e persistência

A cadeia claim → evidence → chunk → página → documento → fonte existe **em memória** (ClaimExtractor re-deriva `document_id`/`page_number`; EvidenceExtractor preserva `chunk_id`/`document_id`/`page_number`). Porém:

- **Não há tabelas de claims nem de evidence** no banco.
- **O plano não é persistido** (`research_plans` e `plan_tasks` vazios após runs reais).
- Apenas **documentos, chunks (com embeddings) e o summary** são persistidos.

**Diagnóstico:** a cadeia de provenance não é persistida, então não pode ser reconstruída após o run. O `ProvenanceResolver` (RDA-029) não tem store de onde partir.

---

## 7. Resultados — Evidence sem validação independente

O `EvidenceExtractor` faz sua própria checagem de grounding, mas o **`EvidenceValidator` (RDA-028) não está conectado** ao pipeline. A evidence é validada apenas pelo mesmo extrator que a produziu (validação de fonte única, sem checagem independente).

---

## 8. Resultados — Serviços órfãos

| Serviço | Ticket | Status | Observação |
|---|---|---|---|
| `ConfidenceScorer` | RDA-027 | **não conectado** | Regras determinísticas. Seus thresholds de bônus de retrieval (0.70/0.85) estão calibrados na mesma escala mal calibrada do retriever — raramente disparariam. |
| `EvidenceValidator` | RDA-028 | **não conectado** | Validação LLM independente claim↔evidence, excluindo o status RDA-026 para evitar viés. |
| `ProvenanceResolver` | RDA-029 | **não conectado** | Sem store persistido de claims/evidence para operar. |

---

## 9. Resultados — Quality gates

O nó de síntese **não tem gate**: com 0 claims, o prompt vira `"(none)"` e o LLM produz um summary tipo "No claims were provided..." (observado no RDA-056). Não há verificação de que existem claims/evidence antes de gerar o summary.

---

## 10. Achado secundário — query de retrieval

O nó de evidence usa `task.title` (tarefa EXTRACT do plano) como query de retrieval, **não a pergunta de pesquisa**. Títulos de tarefas EXTRACT são instruções genéricas de extração ("Extract data on impact metrics from selected studies"), não consultas tópicas focadas — contribui para retrieval fraco.

---

## 11. Veredito consolidado

| Etapa | Qualidade | Evidência |
|---|---|---|
| Embedding (ranking) | **BOM** | R@5=0.93 sem threshold |
| Threshold padrão (0.7) | **CRÍTICO** | R@5 cai para 0.14; ótimo ~0.5–0.55 |
| Document selection | **CRÍTICO** | índice poluído com docs fora do tópico; relevantes perdidos por HTML |
| Download (só PDF) | **ALTO** | relevantes HTML descartados |
| Evidence/Claims | **BOM** | sem alucinação; grounding funciona |
| Provenance (persistência) | **CRÍTICO** | claims/evidence/plano não persistidos |
| Validação independente | **ALTO** | EvidenceValidator não conectado |
| Quality gates | **ALTO** | síntese sem gate de claims/evidence |
| Serviços órfãos | **ALTO** | Confidence/Validation/Provenance não conectados |

**Causa raiz do E2E sem dados (RDA-056):** não é o retrieval nem a evidence — é a **cadeia de seleção/download** que enche o índice com documentos fora do tópico, somada ao **threshold de retrieval mal calibrado** que filtra o pouco conteúdo relevante que chega ao índice.

---

## 12. Artefatos

- `backend/data/benchmarks/retrieval_gold_v1.json` — benchmark gold controlado.
- `backend/scripts/evaluation/run_retrieval_audit.py` — harness de retrieval.
- `backend/scripts/evaluation/run_evidence_audit.py` — harness de evidence/claims.
- `backend/data/evaluation/retrieval_audit_20260827T162303Z.json` — relatório de retrieval.
- `backend/data/evaluation/evidence_audit_20260827T163319Z.json` — relatório de evidence.

**Nenhuma correção de código foi aplicada** (escopo de auditoria). As correções sugeridas (threshold, seleção por relevância, download de HTML, persistência de claims/evidence, gates, conexão dos serviços órfãos) ficam para tickets de implementação.
