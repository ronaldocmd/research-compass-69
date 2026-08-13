# RDA-001 — Monorepo Foundation (Sprint 1)

## Scope delivered

- Monorepo layout: `backend/`, `frontend/`, `docs/`
- FastAPI app with `GET /health` (liveness) and `GET /api/v1/health` (DB-aware)
- PostgreSQL + SQLAlchemy 2.0 engine/session and Alembic environment
- Next.js 15 App Router page rendering backend health
- Docker Compose with `postgres`, `backend`, `frontend`

## Explicitly out of scope

Agents, search providers, PDF handling, embeddings, LangGraph, Redis, Research CRUD.

## Layering rule

```text
API (routes)  ->  Service (business)  ->  Repository (data access)  ->  Database
```

Routes never import SQLAlchemy models or build queries; only repositories execute SQL.

## Adding a migration

```bash
docker compose exec backend alembic revision --autogenerate -m "create research"
docker compose exec backend alembic upgrade head
```

New models go in `backend/app/models/` and must be exported from `app/models/__init__.py`
so `app/db/base.py` exposes them to Alembic autogenerate.
