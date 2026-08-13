import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO if settings.is_development else logging.WARNING)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Application factory. Keeps startup explicit and testable."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness probe. Never touches the database (used by Docker healthcheck)."""
        return {
            "status": "ok",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        }

    logger.info("%s v%s initialised (%s)", settings.PROJECT_NAME, settings.VERSION, settings.ENVIRONMENT)
    return application


app = create_app()
