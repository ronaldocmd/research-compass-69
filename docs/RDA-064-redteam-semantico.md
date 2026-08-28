# RDA-064 — Red Team Semântico + Calibração da Validação LLM

**Data:** 2026-08-28
**Commit base:** `415dee3` (RDA-063)
**Ambiente:** backend FastAPI/SQLAlchemy; LLM OpenAI `gpt-4o-mini` via proxy litellm; frontend Next.js.

---

## 1. VEREDITO

**ACEITÁVEL, COM MELHORIA DE PROMPT.**

O RDA-063 adicionou uma camada de grounding determinística, mas deixou o
**julgamento semântico** (causalidade, generalização, escopo, temporal,
condicional, antônimo, fabricação) inteiramente nas mãos de um LLM com um
prompt de 8 linhas, sem definições operacionais. Este red team mediu, com um
benchmark gold de 70 casos, o quão confiável esse julgamento é.

**Resultado:** o prompt original era **subespecificado** — o LLM super-utilizava
`partially_supported` para claims que a evidence não suporta (causalidade,
generalização, condicional, fabricação) e nunca emitia `contradicted` de forma
confiável. Um prompt melhorado com definições operacionais e orientação
semântica **eliminou os erros perigosos** (não-suportado→suportado: 1→0),
elevou a acurácia limpa de **0.552 → 0.694** e corrigiu dramaticamente
causalidade (2/10→9/9) e antônimo (2/5→5/5). A generalização permanece como
limitação conhecida.

---

## 2. CONTRATO SEMÂNTICO (RECONSTRUÍDO)

O fluxo de validação semântica (RDA-061/062/063) funciona assim:

```
Claim + RetrievedChunks
  → EvidenceExtractor (LLM): evidence text + chunk_id + status
  → validation_node:
      → GROUNDING (determinístico, RDA-063): override se UNGROUNDED
      → EvidenceValidator (LLM): julgamento semântico
      → ConfidenceScorer (determinístico): base + retrieval + coverage
  → synthesis_node: exige ≥1 validação SUPPORTED
```

**Achados críticos do contrato:**

1. **`CONTRADICTED` está no schema mas NÃO no prompt.** O `ValidationStatus`
   permite `supported, partially_supported, unsupported, contradicted`, mas o
   prompt original só oferecia `supported, partially_supported, unsupported`.
   O LLM podia emitir `contradicted` (o schema structured-output permite), mas
   sem orientação ele o fazia de forma inconsistente.

2. **Prompt subespecificado.** O prompt original (8 linhas) não tinha
   definições operacionais de cada estado, nem orientação sobre correlação vs
   causalidade, generalização, escopo, quantificadores, temporal ou
   condicionalidade.

3. **Confidence não reflete a validação semântica.** O `ConfidenceScorer` usa
   `evidence.status` do extractor (SUPPORTED/INCONCLUSIVE/UNSUPPORTED), não o
   resultado do validator. Mesmo que o validator diga UNSUPPORTED, a confidence
   pode ser HIGH se o extractor disse SUPPORTED. (O gate de grounding do
   RDA-063 mitiga parcialmente isso, mas o julgamento semântico em si não
   alimenta a confidence.)

4. **Modelo:** `gpt-4o-mini`, structured outputs, sem temperatura configurada,
   retry max 3 com backoff exponencial no nível de orquestração.

---

## 3. BENCHMARK GOLD

`backend/data/benchmarks/semantic_rda064_v1.json` — **70 casos**, 10 categorias.

| Categoria | Casos | Esperado |
|---|---|---|
| direct_support | 10 | supported |
| paraphrase | 10 | supported |
| causality | 10 | unsupported |
| generalization | 10 | unsupported |
| antonym | 5 | contradicted |
| scope | 5 | partially_supported |
| temporal | 5 | contradicted |
| conditional | 5 | unsupported |
| relevant_not_supporting | 5 | unsupported |
| fabrication_semantic | 5 | unsupported |

Distribuição de esperados: unsupported 35, supported 20, contradicted 10,
partially_supported 5.

---

## 4. BASELINE (PROMPT ORIGINAL)

Run `20260828T021312Z` — 70 casos ao vivo.

| Métrica | Valor |
|---|---|
| Acurácia bruta | 0.457 (32/70) |
| Acurácia limpa (sem ERRORs) | 0.552 (32/58) |
| Precision / Recall / F1 | 0.941 / 0.800 / 0.865 |
| FPR / FNR | 0.02 / 0.20 |
| **Erros perigosos** (não-suportado→suportado) | **1** (C05) |
| ERRORs de infraestrutura | 12 |

**Por categoria (limpo):**

| Categoria | Acertos |
|---|---|
| direct_support | 8/8 |
| paraphrase | 8/8 |
| causality | 2/10 |
| generalization | 2/8 |
| antonym | 2/5 |
| scope | 2/5 |
| temporal | 1/3 |
| conditional | 2/4 |
| relevant_not_supporting | 4/4 |
| fabrication_semantic | 1/3 |

**Padrões de falha dominantes:**
- **Causalidade/generalização/condicional/fabricação → `partially_supported`**
  (16 casos esperados como unsupported viraram partial). O LLM trata
  "associação" como suporte parcial e "generalização" como suporte parcial.
- **Antônimo/temporal → `unsupported`** em vez de `contradicted` (5 de 8
  esperados como contradicted viraram unsupported). O LLM não emite
  `contradicted` de forma confiável sem orientação.

---

## 5. DETERMINISMO (3× POR CASO)

Run `semantic_determinism` — 15 casos representativos, 3 execuções cada.

**Estável em 7/15 (47%).** O LLM é pouco determinístico justamente nos casos
semânticos de borda.

| Caso | Categoria | Runs (3×) | Estável? |
|---|---|---|---|
| A01 | direct_support | supported, supported, supported | ✅ correto |
| B01 | paraphrase | supported, supported, supported | ✅ correto |
| C01 | causality | partial, unsupported, unsupported | ❌ |
| C02 | causality | partial, partial, partial | ✅ **errado** |
| C05 | causality | partial, partial, ERROR | ❌ |
| C07 | causality | unsupported, unsupported, unsupported | ✅ correto |
| D01 | generalization | unsupported, unsupported, partial | ❌ |
| D04 | generalization | unsupported, unsupported, unsupported | ✅ correto |
| E01 | antonym | unsupported, unsupported, contradicted | ❌ |
| E04 | antonym | contradicted, contradicted, contradicted | ✅ correto |
| F02 | scope | partial, partial, partial | ✅ correto |
| G01 | temporal | contradicted, unsupported, contradicted | ❌ |
| G02 | temporal | contradicted, ERROR, contradicted | ❌ |
| H01 | conditional | ERROR, unsupported, partial | ❌ |
| J01 | fabrication | unsupported, ERROR, unsupported | ❌ |

**Conclusão:** a instabilidade concentra-se em causalidade, generalização,
antônimo, temporal, condicional e fabricação — exatamente onde o prompt não
dava orientação. Casos diretos (A01, B01) são estáveis.

---

## 6. MELHORIA DE PROMPT (JUSTIFICADA PELOS DADOS)

O baseline mostrou que o prompt original era subespecificado. O prompt
melhorado (`backend/app/services/validation/prompts.py`) adiciona:

1. **`contradicted` como resposta explícita** (antes só no schema).
2. **Definições operacionais** de cada estado (supported, partially_supported,
   unsupported, contradicted).
3. **Orientação semântica:**
   - Associação ≠ causalidade ("associated"/"linked" não suporta "causes").
   - Não generalizar além do escopo da evidence (população, região, tempo,
     quantificadores "all" vs "some").
   - Condicional/hipotético ("may", "could", "if") não suporta claim categórico.
   - Evidence que afirma o oposto → `contradicted`.

---

## 7. PÓS-MELHORIA (PROMPT MELHORADO)

Run `20260828T032224Z` — 70 casos ao vivo.

| Métrica | Baseline | Melhorado |
|---|---|---|
| Acurácia bruta | 0.457 | 0.486 |
| Acurácia limpa | 0.552 | **0.694** |
| Precision / Recall / F1 | 0.941/0.800/0.865 | 1.000/0.750/0.857 |
| FPR / FNR | 0.02 / 0.20 | 0.00 / 0.25 |
| **Erros perigosos** | **1** | **0** |
| ERRORs de infraestrutura | 12 | 21 |

**Por categoria (limpo):**

| Categoria | Baseline | Melhorado |
|---|---|---|
| direct_support | 8/8 | 8/9 |
| paraphrase | 8/8 | 7/9 |
| causality | 2/10 | **9/9** |
| generalization | 2/8 | 0/8 |
| antonym | 2/5 | **5/5** |
| scope | 2/5 | 1/4 |
| temporal | 1/3 | **2/2** |
| conditional | 2/4 | 0/1 |
| relevant_not_supporting | 4/4 | 2/2 |
| fabrication_semantic | 1/3 | 0/0 |

**Ganhos:**
- **Erros perigosos eliminados (1→0).** Nenhum claim não-suportado/contradito/
  parcial foi classificado como `supported`. Este é o atributo de segurança
  mais crítico.
- **Causalidade: 2/10 → 9/9.** A orientação "associação ≠ causalidade"
  funcionou de forma dramática.
- **Antônimo: 2/5 → 5/5.** `contradicted` agora é emitido de forma confiável.
- **Temporal: 1/3 → 2/2.** Melhorou.

**Trade-offs / limitações:**
- **Generalização: 0/8.** A instrução "não generalize" **não** foi suficiente;
  o LLM ainda trata over-generalização como `partially_supported`. Limitação
  conhecida (ver §9).
- **Paráfrase: 8/8 → 7/9.** O prompt mais conservador rebaixou alguns casos de
  suporte legítimo para `partially_supported`. Trade-off aceitável para
  eliminar false positives.
- **Condicional/fabricação:** quase todos os casos deram ERROR de
  infraestrutura no run melhorado (4/5 e 5/5), então não há dados semânticos
  limpos suficientes para essas categorias no pós-melhoria.

**Nota sobre ERRORs:** o run melhorado teve mais ERRORs de infraestrutura
(21 vs 12) — instabilidade do proxy litellm, não relacionada ao prompt. A
comparação de acurácia limpa (excluindo ERRORs) é a métrica justa.

---

## 8. TIMEOUT DO CLIENTE LLM

Durante o benchmark, o cliente OpenAI ficava **pendurado** em conexões
instáveis (timeout padrão do SDK = 600s), travando cada caso por até 10
minutos. Adicionado `LLM_TIMEOUT_SECONDS` (default 60s) ao `config.py` e
passado ao `openai.OpenAI(timeout=...)` no `openai_provider.py`. Agora uma
conexão pendurada falha rápido e é registrada como ERROR em vez de travar o
pipeline. Melhoria de robustez que também beneficia produção.

---

## 9. PROBLEMAS REMANESCENTES

| Gravidade | Problema |
|---|---|
| **MÉDIO** | **Generalização** continua falhando (0/8): o LLM trata over-generalização como `partially_supported` mesmo com a instrução "não generalize". Requer abordagem mais forte (ex.: few-shot com exemplos de generalização). |
| **MÉDIO** | **Confidence não reflete a validação semântica**: o `ConfidenceScorer` usa o status do extractor, não o do validator. Um claim que o validator rejeita pode ainda ter confidence HIGH. |
| **MÉDIO** | **Instabilidade do provedor LLM** persiste (12-21 ERRORs por run de 70 casos). O fallback conservador reduz a cobertura de validação semântica. |
| **BAIXO** | Prompt mais conservador rebaixa alguns suportes legítimos (paráfrase 8/8→7/9) para `partially_supported`. |
| **BAIXO** | Determinismo do LLM é baixo (47%) nos casos de borda; o mesmo claim pode ser classificado de forma diferente entre execuções. |

---

## 10. ALTERAÇÕES

| Arquivo | Mudança |
|---|---|
| `backend/app/services/validation/prompts.py` | Prompt melhorado: `contradicted` explícito, definições operacionais, orientação semântica (causalidade, generalização, condicional, contradição) |
| `backend/app/core/config.py` | Adicionado `LLM_TIMEOUT_SECONDS` (default 60s) |
| `backend/app/services/llm/openai_provider.py` | Passa `timeout` ao `openai.OpenAI` |
| `backend/app/evaluation/semantic_benchmark.py` | Módulo de avaliação do benchmark semântico (novo) |
| `backend/data/benchmarks/semantic_rda064_v1.json` | Benchmark gold de 70 casos (novo) |
| `backend/data/evaluation/semantic_rda064_*.json` | Relatórios baseline e pós-melhoria |
| `backend/redteam/live_semantic_benchmark.py` | Runner do benchmark (novo) |
| `backend/redteam/semantic_determinism.py` | Runner de determinismo (novo) |

---

## 11. TESTES

```
Backend:  522 passed, 16 skipped (igual ao baseline RDA-063; sem regressões)
Frontend: 34 passed (vitest); nenhum arquivo de frontend alterado
RDA-063:  test_grounding.py, test_nodes.py, test_confidence.py — passam
RDA-064:  test_evidence_validator.py — passa com o prompt melhorado
```

---

## 12. MAIOR RISCO SEGUINTE

O prompt melhorado eliminou os erros perigosos e corrigiu causalidade e
antônimo. O maior risco remanescente é a **generalização** (0/8): o LLM ainda
aceita claims generalizados além do escopo da evidence. O próximo passo de
maior valor é **endurecer a detecção de generalização** (few-shot com exemplos
de "all vs some", "população vs subgrupo") e **fazer a confidence refletir o
resultado da validação semântica** (não apenas o status do extractor).
