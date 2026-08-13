# RDA-003 — Consolidação do Backend FastAPI (Sprint 1)

## Escopo entregue

Consolidação da fundação FastAPI: inicialização, configuração, CORS, camadas e
testes. Nenhuma funcionalidade de Sprint 2+ (sem Research CRUD/Model, busca,
PDFs, embeddings, Redis, LangGraph ou agentes).

## Endpoints (contrato preservado)

| Rota              | Toca o banco | Uso                                        |
| ----------------- | ------------ | ------------------------------------------ |
| `GET /health`     | Não          | Liveness (healthcheck do Dockerfile)       |
| `GET /api/v1/health` | Sim (`SELECT 1`) | Health check com verificação do PostgreSQL |

`/api/v1/health` responde `200` sempre; `status` é `ok` com `database: "up"` e
`degraded` com `database: "down"` — falhas de conexão são capturadas no
repositório, nunca vazam como 500.

## Alterações

- `app/main.py`: application factory `create_app()`, logging conforme
  `ENVIRONMENT`, CORS via `settings.cors_origins_list`, `/redoc` habilitado.
- `app/core/config.py`: `case_sensitive`, suporte a `BACKEND_CORS_ORIGINS="*"`,
  helper `is_development`.
- `app/db/session.py`: engine/sessionmaker **lazy** (`lru_cache`) — importar o
  app não exige mais driver/banco disponível (evita crash na inicialização e
  permite testes sem PostgreSQL).
- `app/schemas/health.py`: tipos `Literal` + campo `environment`.
- `app/services/health_service.py`: deriva `status` de `database`.
- `app/repositories/health_repository.py`: log de aviso ao falhar o ping.
- `tests/conftest.py`: `TestClient` + override de `get_db` com SQLite em memória.
- `tests/test_health.py`: 6 testes.
- `backend/pytest.ini`: `pythonpath=.`, `testpaths=tests`.

Camadas preservadas: API -> Service -> Repository -> Database (somente o
repositório executa SQL). Frontend e Docker do RDA-002 intactos.

## Validações executadas

```text
$ python -m pytest -q      # 6 passed
```

Cobrem: liveness sem banco, health v1 com banco up, degradação com banco down,
captura de `SQLAlchemyError` no repositório, header CORS e superfície do OpenAPI
(apenas as duas rotas de health).

## Limitações

Sem Docker daemon neste ambiente: `docker compose up --build`,
`alembic upgrade head` e o healthcheck do container não foram executados aqui.
Os testes rodaram com um interpretador Python local e SQLite em memória (o
`SELECT 1` do health é compatível com ambos os bancos). Validar localmente:

```bash
docker compose up --build
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health
docker compose exec backend pytest -q
```
