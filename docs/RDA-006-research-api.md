# RDA-006 — Research API

Backend-only CRUD para a entidade `Research`, preservando a separação
**API → Service → Repository → Database**. Nada de frontend, agentes, busca,
PDFs, embeddings, pgvector, Redis ou LangGraph.

## Camadas

| Camada     | Arquivo                                        | Responsabilidade                          |
| ---------- | ---------------------------------------------- | ----------------------------------------- |
| API        | `backend/app/api/v1/endpoints/researches.py`   | HTTP, status codes, mapeamento de 404     |
| Service    | `backend/app/services/research_service.py`     | regras de negócio, `ResearchNotFoundError`|
| Repository | `backend/app/repositories/research_repository.py` | único acesso ao banco (SQLAlchemy 2.x) |
| Schemas    | `backend/app/schemas/research.py`              | validação de request/response (Pydantic v2)|

## Endpoints (`/api/v1/researches`)

| Método | Rota                          | Sucesso | Erros                          |
| ------ | ----------------------------- | ------- | ------------------------------ |
| POST   | `/api/v1/researches`          | 201     | 422 (validação)                |
| GET    | `/api/v1/researches`          | 200     | 422 (`limit`/`offset` inválidos) |
| GET    | `/api/v1/researches/{id}`     | 200     | 404, 422 (UUID inválido)       |
| PATCH  | `/api/v1/researches/{id}`     | 200     | 404, 422                       |
| DELETE | `/api/v1/researches/{id}`     | 204     | 404, 422                       |

Listagem ordenada por `created_at DESC`, com paginação `limit` (1–200, default 50)
e `offset` (≥ 0).

## Validação

- `id` deve ser UUID válido (FastAPI → 422 quando não for).
- `title`: obrigatório, 1–200 caracteres.
- `objective` e `question`: obrigatórios, não vazios.
- `status`: apenas `DRAFT` e `READY`; default `DRAFT`.
- `extra="forbid"`: campos desconhecidos são rejeitados com 422.
- PATCH é parcial (`exclude_unset`); corpo vazio devolve o recurso inalterado.

## Testes

`backend/tests/test_research_api.py`:

- Unitários (sem banco): defaults de status, limite de 200 caracteres, campos
  obrigatórios, status inválido, natureza parcial do PATCH.
- Integração com PostgreSQL real (fixture `pg_client`, via `TEST_DATABASE_URL`):
  CRUD completo, UUID gerado, timestamps, 404 em GET/PATCH/DELETE inexistentes,
  422 para UUID inválido e payloads inválidos, paginação e health endpoints
  continuando ok.

Execução local:

```bash
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec -e TEST_DATABASE_URL="$DATABASE_URL" backend pytest
```

Sem `TEST_DATABASE_URL` os testes de integração são marcados como *skipped*;
os unitários e os de health continuam rodando.
