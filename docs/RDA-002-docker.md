# RDA-002 — Docker (Sprint 1)

## Escopo entregue

Infraestrutura real de containerização para a fundação RDA-001. Nenhuma
funcionalidade de Sprint 2+ (sem Research CRUD, agentes, busca, PDFs,
embeddings, Redis ou LangGraph).

## Arquivos

| Arquivo                | Papel                                                        |
| ---------------------- | ------------------------------------------------------------ |
| `backend/Dockerfile`   | Python 3.12-slim, deps via `requirements.txt`, uvicorn :8000 |
| `backend/.dockerignore`| Exclui venv/caches/`.env` do contexto de build                |
| `frontend/Dockerfile`  | Node 22-slim, `npm install`, `next dev` :3000                 |
| `frontend/.dockerignore`| Exclui `node_modules`/`.next`/`.env`                         |
| `docker-compose.yml`   | Serviços `postgres`, `backend`, `frontend` + rede + volume    |
| `.env.example`         | Todas as variáveis, sem segredos reais                        |

## Decisões de Docker

- **Base images fixas**: `python:3.12-slim`, `node:22-slim`, `postgres:16-alpine`.
- **Camadas de dependência**: `requirements.txt` / `package.json` copiados antes
  do código para aproveitar cache de build.
- **Healthchecks**: `pg_isready` no Postgres; `curl /health` no backend (usa o
  endpoint de liveness preservado do RDA-001); `curl /` no frontend. `curl` é
  instalado nas imagens apenas para isso.
- **Ordem de inicialização**: `depends_on` com `condition: service_healthy`
  (`backend` espera Postgres saudável; `frontend` espera backend saudável).
- **Rede interna** `rda-net` (bridge): serviços se resolvem por nome DNS
  (`postgres`, `backend`).
- **Persistência**: volume nomeado `postgres_data`.
- **Sem hard-code de credenciais**: `POSTGRES_USER/PASSWORD/DB` são
  obrigatórios (`${VAR:?}`) e vêm do `.env`; nenhum default de senha no compose.
- **DATABASE_URL** injetada por ambiente no backend (lida por
  `app/core/config.py`); frontend recebe `NEXT_PUBLIC_API_URL` (browser) e
  `API_INTERNAL_URL` (server-side, via rede interna).
- **Modo desenvolvimento**: bind mounts (`./backend:/app`, `./frontend:/app`
  com `node_modules` anônimo) e `--reload` / `next dev` para hot reload. Build
  multi-stage de produção fica para uma etapa posterior de deploy.
- **Execução como root nos containers de dev**: intencional, para evitar
  conflitos de UID com os bind mounts do host (alembic/next escrevem no volume).

## Validações executadas

- Sintaxe/estrutura do `docker-compose.yml` validada por parse YAML
  (serviços, rede `rda-net`, volume `postgres_data`, healthchecks e
  `depends_on` conferidos).
- Revisão estática dos Dockerfiles e alinhamento das variáveis do `.env.example`
  com `app/core/config.py` e `frontend/lib/api.ts`.
- Confirmado que `.env` está no `.gitignore` e que nenhum segredo real foi
  adicionado.

## Não executado (limitação de ambiente)

O ambiente do Lovable não possui Docker daemon, runtime Python nem servidor
Next.js. Portanto **não** foi possível rodar `docker compose config`,
`docker compose up --build`, `pytest` ou `alembic upgrade head` aqui. Valide
localmente/CI com:

```bash
cp .env.example .env
docker compose config      # validação completa de interpolação
docker compose up --build
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health
```
