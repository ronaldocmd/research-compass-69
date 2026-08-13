# Research Discovery Agent — RDA-001

Executable foundation of the MVP monorepo.

| Layer    | Stack                                     |
| -------- | ----------------------------------------- |
| Backend  | Python 3.12 + FastAPI                     |
| Frontend | Next.js 15 + TypeScript (App Router)      |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 + Alembic  |
| Runtime  | Docker Compose                            |

## Structure

```text
backend/
  app/{api/v1,core,db,models,repositories,schemas,services}
  alembic/            # migration environment
  tests/
frontend/
  app/ components/ lib/ types/ tests/
docs/
docker-compose.yml
.env.example
```

## Run with Docker (RDA-002)

```bash
cp .env.example .env   # ajuste POSTGRES_PASSWORD; .env nunca é comitado
docker compose up --build
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- DB-aware health: http://localhost:8000/api/v1/health
- PostgreSQL: localhost:5432 (dentro da rede `rda-net`: host `postgres`)

Infra de containers:

- Rede interna `rda-net` (bridge) conecta `postgres`, `backend` e `frontend`.
- Volume nomeado `postgres_data` persiste os dados do PostgreSQL 16.
- Healthchecks: `pg_isready` (postgres), `/health` (backend), `/` (frontend).
- Ordem de inicialização: `postgres` (healthy) -> `backend` (healthy) -> `frontend`.
- Sem credenciais hard-coded: todas as variáveis vêm de `.env` (`DATABASE_URL` no
  backend, `NEXT_PUBLIC_API_URL` / `API_INTERNAL_URL` no frontend). Portas
  configuráveis via `POSTGRES_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`.

> Nota sobre o preview do Lovable: o preview roda apenas a página web embutida
> (Vite/TanStack). Não há Docker daemon, Python nem Next.js server nesse ambiente,
> portanto `docker compose up` e os endpoints acima só funcionam localmente/CI.


## Run without Docker

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=postgresql+psycopg://rda:rda@localhost:5432/rda uvicorn app.main:app --reload

# frontend
cd frontend
npm install && npm run dev
```

## Migrations (RDA-004)

`DATABASE_URL` vem sempre do ambiente; o Alembic lê `app.core.config.settings` e usa
`app.db.base.Base.metadata` como target de autogenerate. A revisão inicial
`0001_baseline` é vazia de propósito: apenas cria a tabela `alembic_version` (a tabela
de Research chega em RDA-005). Detalhes em `docs/RDA-004-database.md`.

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current   # -> 0001_baseline (head)
docker compose exec backend alembic heads
docker compose exec backend alembic revision --autogenerate -m "message"
```


## Tests

```bash
docker compose exec backend pytest
cd frontend && npm test
```

## Architecture rule

`API -> Service -> Repository -> Database`. Out of scope for RDA-001: agents, search,
PDFs, embeddings, LangGraph, Redis, Research CRUD.
