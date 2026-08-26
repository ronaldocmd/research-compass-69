# RDA-054 — Análise e Otimização de Performance

Análise de performance do Research Discovery Agent, com medição antes de
qualquer otimização. O princípio seguido foi: **medir primeiro, otimizar
apenas com evidência** — nenhuma mudança especulativa foi feita.

## Resumo

| Item | Resultado |
| ---- | --------- |
| Gargalo medido | Cálculo de similaridade cosseno no `DocumentRetriever` (CPU-bound, puro Python) |
| Otimização aplicada | Cache de normas L2 dos embeddings dos chunks |
| Speedup medido | **2.4x–3.0x** no scoring de retrieval (índice de 1k–5k chunks) |
| Correção de defeito | `DocumentRetriever` copiava o índice, deixando-o vazio em produção |
| Endpoints API | Sem gargalo (5–14 ms em escala MVP) |
| Frontend | Sem gargalo (sem polling, sem fetch redundante) |

## Metodologia

1. **Setup**: estado do git, histórico, estrutura, configuração.
2. **Baseline**: suíte de testes antes das mudanças — **459 passed, 16 skipped**.
3. **Inspeção da arquitetura**: pipeline (planning → search → processing →
   evidence → synthesis), serviços, repositórios, modelos.
4. **Medição**:
   - Endpoints API (com banco vazio e com dados de teste).
   - Cálculo de similaridade cosseno em índices sintéticos de 100–5000 chunks.
   - Análise estática de queries, índices, N+1, frontend.
5. **Otimização** com a menor mudança possível + testes de regressão.
6. **Verificação**: suíte completa após as mudanças — **461 passed, 16 skipped**.

## Medições

### Endpoints API (FastAPI, host local, PostgreSQL)
Com o banco vazio e com 5 pesquisas de teste (média de 10 requisições):

| Endpoint | Latência média |
| -------- | -------------- |
| `GET /api/v1/researches` | ~13.6 ms |
| `GET /api/v1/researches/{id}` | ~7.7 ms |
| `GET /api/v1/researches/{id}/cost` | ~8.9 ms |
| `GET /api/v1/researches/{id}/performance` | ~13.1 ms |

Nenhum gargalo em escala MVP. As queries são simples e indexadas
(`documents.research_id`, `chunks.document_id`). Sem N+1 nos endpoints de
listagem/detalhe.

### Retrieval — similaridade cosseno (CPU-bound)
O `DocumentRetriever` calcula similaridade cosseno em puro Python (sem numpy,
por design) contra um índice em memória. Medição com embeddings de 1536
dimensões:

| Índice (chunks) | Antes (ms) | Depois (ms) | Speedup |
| --------------- | ---------- | ----------- | ------- |
| 1.000 | 124.8 | 51.7 | 2.41x |
| 5.000 | 752.4 | 252.8 | 2.98x |

O custo dominante era recomputar a norma L2 (`sqrt(sum(x*x))`) de **cada**
chunk a **cada** consulta. Como os embeddings dos chunks são imutáveis após a
indexação, as normas são cacheadas e só recalculadas para chunks adicionados
depois da última sincronização.

### Pipeline (planning → search → processing → evidence → synthesis)
O custo dominante é **I/O externo** (chamadas LLM, busca OpenAlex/Crossref,
downloads, embeddings), não código CPU-bound do app. Não há gargalo de CPU
mensurável além do retrieval. Paralelizar documentos/queries exigiria
sessões de banco thread-safe e é explicitamente desencorajado sem medição;
documentado como melhoria futura.

### Frontend (Next.js)
Sem polling, sem fetch redundante. Server components usam `cache: "no-store"`
(uma requisição por render). `getBackendHealth` é chamado uma vez na landing
page. Sem gargalo.

## Otimizações aplicadas

### 1. Cache de normas L2 no `DocumentRetriever` (RDA-054)
`backend/app/services/retrieval/retriever.py`:
- Novo `_norms: list[float]` cacheado no retriever.
- `_sync_norms()` estende o cache quando o índice cresce.
- `_l2_norm()` e `_cosine_with_norms()` reutilizam as normas pré-computadas.
- A norma da query também é computada uma única vez por consulta.
- Resultado idêntico ao `cosine_similarity` de referência (verificado por teste).

### 2. Correção: índice compartilhado no `DocumentRetriever`
`backend/app/services/retrieval/retriever.py`:
- `self._index = list(index)` copiava o índice, deixando o retriever
  permanentemente vazio em produção (o `WorkflowServices` passa uma lista
  compartilhada que o processador popula durante o processamento).
- Alterado para manter a referência (`self._index = index`), conforme o
  comentário do próprio `wiring.py` ("Shared, mutable retrieval index").
- Sem essa correção, o estágio de evidence nunca teria chunks para recuperar,
  e a otimização de cache de normas seria código morto em produção.

## Testes de regressão
`backend/tests/test_retrieval.py`:
- `test_retrieve_matches_reference_cosine_similarity` — o scoring com normas
  cacheadas é idêntico ao `cosine_similarity` de referência.
- `test_retrieve_syncs_norm_cache_when_index_grows` — chunks adicionados após
  a construção são pontuados corretamente (cache sincroniza com o índice).

## Verificação

- Baseline: **459 passed, 16 skipped**.
- Após mudanças: **461 passed, 16 skipped** (2 novos testes de retrieval).
- Frontend: **34 passed** (inalterado).
- Speedup medido no retrieval: **2.4x–3.0x** (índice de 1k–5k chunks).

## Melhorias futuras (não implementadas — sem evidência de gargalo no MVP)
- **Paralelizar processamento de documentos** (`processing_node`): cada
  documento é independente, mas exige sessões de banco thread-safe e
  tratamento do índice compartilhado. Alto risco; só justificado se o I/O
  externo dominar o tempo de parede em escala real.
- **Paralelizar queries de busca** (`search_node`): poucas queries por run;
  ganho marginal.
- **Substituir o índice em memória por pgvector**: elimina o custo de
  similaridade em Python, mas adiciona dependência de extensão PostgreSQL.
- **`pip-audit` em CI**: não instalado (evitando novas dependências).
