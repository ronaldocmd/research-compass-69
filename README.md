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

## Run

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- DB-aware health: http://localhost:8000/api/v1/health

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

## Migrations

```bash
docker compose exec backend alembic revision --autogenerate -m "message"
docker compose exec backend alembic upgrade head
```

## Tests

```bash
docker compose exec backend pytest
cd frontend && npm test
```

## Architecture rule

`API -> Service -> Repository -> Database`. Out of scope for RDA-001: agents, search,
PDFs, embeddings, LangGraph, Redis, Research CRUD.
