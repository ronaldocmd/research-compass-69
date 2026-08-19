from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    PROJECT_NAME: str = "Research Discovery Agent"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+psycopg://rda:rda@localhost:5432/rda"
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000"

    # OpenAlex search provider (RDA-012). No API key required; an email is
    # recommended by OpenAlex to get into their "polite pool" (higher rate limit).
    OPENALEX_BASE_URL: str = "https://api.openalex.org"
    OPENALEX_EMAIL: str | None = None
    OPENALEX_TIMEOUT_SECONDS: float = 10.0

    # Crossref search provider (RDA-013). No API key required; an email is
    # recommended by Crossref to get into their "polite pool" (higher rate limit).
    CROSSREF_BASE_URL: str = "https://api.crossref.org"
    CROSSREF_EMAIL: str | None = None
    CROSSREF_TIMEOUT_SECONDS: float = 10.0

    # Document downloader (RDA-018).
    DOWNLOAD_TIMEOUT_SECONDS: float = 30.0
    DOWNLOAD_MAX_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    DOWNLOAD_ALLOWED_CONTENT_TYPES: str = (
        "application/pdf,text/html,application/octet-stream"
    )

    # File storage (RDA-019).
    STORAGE_BASE_DIR: str = "storage/documents"

    # Chunking (RDA-022). Size is in characters, not tokens, to keep the
    # strategy dependency-free and deterministic.
    CHUNK_SIZE_CHARS: int = 1000
    CHUNK_STRATEGY: str = "structure_aware"

    # Embeddings (RDA-023).
    EMBEDDING_PROVIDER: str = "openai"
    OPENAI_API_KEY: str | None = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_BATCH_SIZE: int = 100

    # Retrieval (RDA-024). Default top-K and minimum cosine-similarity
    # threshold for DocumentRetriever; both can be overridden per-call.
    RETRIEVAL_TOP_K: int = 5
    RETRIEVAL_MIN_SCORE: float = 0.7

    # LLM (RDA-025). Completion model used by ClaimExtractor (and later
    # evidence/synthesis steps).
    LLM_MODEL: str = "gpt-4o-mini"

    # Planning (RDA-030). Bounds for the number of tasks a plan may contain.
    PLANNING_MIN_TASKS: int = 3
    PLANNING_MAX_TASKS: int = 10

    @property
    def cors_origins_list(self) -> list[str]:
        """Comma-separated origins -> list. Supports the wildcard '*'."""
        raw = self.BACKEND_CORS_ORIGINS.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() in {"development", "dev", "local"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
