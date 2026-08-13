# RDA-005 — Modelo `Research` + primeira migration de domínio (Sprint 1)

## Escopo entregue

Model SQLAlchemy 2.x `Research`, enum `research_status` (apenas `DRAFT` e `READY`),
migration `0002_research` e testes de modelo/persistência. Sem Repository, Service,
API CRUD, telas, busca, PDFs, embeddings, Redis, LangGraph ou agentes.

## Arquivos criados/alterados

| Arquivo | Mudança |
| ------- | ------- |
| `backend/app/models/research.py` | Criado: `ResearchStatus` (str, Enum) + model `Research` |
| `backend/app/models/__init__.py` | Exporta `Research`/`ResearchStatus` (registro em `Base.metadata`) |
| `backend/alembic/versions/20260813_0002_research.py` | Criado: tabela `researches` + tipo enum + índice; downgrade completo |
| `backend/tests/test_research_model.py` | Criado: testes de modelo e de persistência em PostgreSQL |
| `backend/tests/test_db_connection.py` | Ajuste: metadata agora contém `researches` |
| `docs/RDA-005-research-model.md` | Este documento |

Inalterados: health endpoints (`/health`, `/api/v1/health`), Docker/compose, frontend.

## Schema final de `researches`

```text
   Column   |           Type           | Nullable |         Default
------------+--------------------------+----------+--------------------------
 id         | uuid                     | not null | gen_random_uuid()
 title      | character varying(200)   | not null |
 objective  | text                     | not null |
 question   | text                     | not null |
 status     | research_status          | not null | 'DRAFT'::research_status
 created_at | timestamp with time zone | not null | now()
 updated_at | timestamp with time zone | not null | now()
Indexes:
    "pk_researches" PRIMARY KEY, btree (id)
    "ix_researches_status" btree (status)
Type: research_status = ENUM ('DRAFT', 'READY')
```

Decisões:
- UUID nativo do PostgreSQL; default duplo — `uuid.uuid4` no lado Python e
  `gen_random_uuid()` no servidor (extensão `pgcrypto` criada pela migration).
- Enum nativo `research_status` com apenas `DRAFT`/`READY`; `validate_strings=True`
  rejeita valores fora do enum antes do INSERT.
- `created_at` com `server_default now()`; `updated_at` com `server_default now()` +
  `onupdate=func.now()` (atualizado pelo ORM em qualquer alteração).
- Único índice adicional: `ix_researches_status` (listagem por status, único padrão
  de acesso conhecido nesta etapa). Nenhuma constraint especulativa.

## Migration

`0002_research` (revises `0001_baseline`): cria extensão `pgcrypto` (idempotente),
cria o tipo enum (`checkfirst=True`), cria a tabela e o índice.
`downgrade()`: remove índice, tabela e então o tipo enum com `checkfirst=True`
(`create_type=False` no ENUM evita criação implícita/duplicada pelo `create_table`).

## Validações executadas (PostgreSQL real)

Cluster PostgreSQL 17.9 iniciado no sandbox (socket unix, usuário não-root):

```text
alembic upgrade head   -> 0001_baseline -> 0002_research
alembic current        -> 0002_research (head)
alembic heads          -> 0002_research (head)
\d researches / \dT    -> schema e enum conforme acima
alembic_version        -> 0002_research
alembic downgrade base -> OK (tabela e enum removidos)
alembic upgrade head   -> OK (idempotente)
pytest                 -> 22 passed
```

Testes de persistência (executados contra o PostgreSQL real via `TEST_DATABASE_URL`):
criação válida, UUID gerado, timestamps com timezone, round-trip dos dois status,
`updated_at` alterado em UPDATE, campo obrigatório ausente -> `IntegrityError`,
`title` com 201 chars -> `DataError`, status inválido rejeitado, e comparação do
schema real do banco com o model.

## Limitações de runtime

- Sem Docker daemon no ambiente: `docker compose up --build` segue validado apenas
  estaticamente.
- O cluster de validação é PostgreSQL 17.9 (binário do sandbox); o compose usa
  `postgres:16-alpine`. Confirme localmente com
  `docker compose exec backend alembic upgrade head`.

## Como executar localmente

```bash
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
docker compose exec backend pytest
```
