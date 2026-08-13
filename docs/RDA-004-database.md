# RDA-004 — PostgreSQL + SQLAlchemy + Alembic (Sprint 1)

## Escopo entregue

Consolidação da camada de dados e primeira migration (baseline). Sem Research
Model/tabela (RDA-005), sem CRUD, busca, PDFs, embeddings, Redis, LangGraph ou agentes.

## Arquivos criados/alterados

| Arquivo | Mudança |
| ------- | ------- |
| `backend/alembic/env.py` | URL vinda apenas de `settings.DATABASE_URL` (escape de `%`), `Base.metadata` como target, `compare_type` + `compare_server_default` |
| `backend/alembic/versions/20260813_0001_baseline.py` | Migration inicial `0001_baseline` (vazia) |
| `backend/tests/test_db_connection.py` | Testes da camada SQLAlchemy + teste real de PostgreSQL (opt-in via `TEST_DATABASE_URL`) |
| `backend/requirements.txt` | `SQLAlchemy` 2.0.36 -> 2.0.43 (compatibilidade psycopg 3.2 / PostgreSQL 16+) |
| `docs/RDA-004-database.md` | Este documento |

Inalterados: `docker-compose.yml` (PostgreSQL 16, volume `postgres_data`, healthcheck
`pg_isready`), health endpoints (`/health`, `/api/v1/health`), frontend, Dockerfiles.

## Configuração SQLAlchemy adotada

- `app/db/base.py`: única `Base(DeclarativeBase)`; importa `app.models` para que o
  Alembic descubra o metadata quando os modelos existirem.
- `app/db/session.py`: `get_engine()` e `get_sessionmaker()` com `lru_cache`
  (criação lazy — importar o app não exige driver nem banco vivo);
  `pool_pre_ping=True`; `get_db()` como dependência FastAPI (uma sessão por request).
- `DATABASE_URL` exclusivamente por ambiente (`app/core/config.py` / `.env`),
  sem credenciais hard-coded em código, `alembic.ini` ou compose.

## Migration criada

`0001_baseline` — `upgrade()`/`downgrade()` vazios. Propósito: fixar o início da
cadeia de revisões e criar a tabela `alembic_version` no PostgreSQL, permitindo que
`alembic upgrade head`, `alembic current` e `alembic heads` fiquem coerentes antes de
existir qualquer tabela de domínio. A tabela `researches` entra como próxima revisão
em RDA-005 — nenhuma tabela futura foi inventada aqui.

## Validações executadas (com PostgreSQL real no ambiente)

Foi possível iniciar um cluster PostgreSQL local (17.9, socket unix) e rodar o Alembic:

```text
alembic current          -> (vazio, antes do upgrade)
alembic upgrade head     -> Running upgrade  -> 0001_baseline
alembic current          -> 0001_baseline (head)
alembic heads            -> 0001_baseline (head)
SELECT * FROM alembic_version -> 0001_baseline
alembic downgrade base   -> OK
alembic upgrade head     -> OK (idempotente)
pytest                   -> 11 passed
```

## Limitações de runtime

- Não há Docker daemon no ambiente Lovable: `docker compose up --build` e o
  healthcheck do serviço `postgres` continuam validados apenas estaticamente.
- O cluster usado nos testes foi PostgreSQL 17.9 (binário disponível no sandbox);
  o compose permanece em `postgres:16-alpine`. Rode localmente
  `docker compose exec backend alembic upgrade head` para confirmar no 16.
- Bancos com encoding `SQL_ASCII` fazem o psycopg retornar bytes; use `UTF8`
  (padrão da imagem oficial do PostgreSQL).

## Como executar localmente

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
docker compose exec backend pytest
```
