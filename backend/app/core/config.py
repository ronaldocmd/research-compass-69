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

    # Multi-source search (RDA-066). Comma-separated provider names queried in
    # parallel by SearchService.search_all; providers that need a key (CORE) are
    # skipped when it is missing.
    SEARCH_PROVIDERS: str = "openalex,crossref,semantic_scholar,arxiv,europe_pmc,core"

    # Semantic Scholar (RDA-066). The key is optional; it only raises the rate limit.
    SEMANTIC_SCHOLAR_BASE_URL: str = "https://api.semanticscholar.org/graph/v1"
    SEMANTIC_SCHOLAR_API_KEY: str | None = None
    SEMANTIC_SCHOLAR_TIMEOUT_SECONDS: float = 10.0
    # Semantic Scholar's published limit is 1 request/second, cumulative
    # across every endpoint (keyed or not). SearchService fans a research's
    # queries out to every enabled provider, so without process-wide spacing
    # here a burst trips 429s and this source silently drops out of that
    # query's results (error isolation in SearchService.search_all).
    SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS: float = 1.0

    # arXiv (RDA-066). No key. arXiv asks for modest request rates.
    ARXIV_BASE_URL: str = "https://export.arxiv.org"
    ARXIV_TIMEOUT_SECONDS: float = 15.0
    # arXiv's usage policy: at most one request every 3 seconds. Bursts get
    # refused (HTTP 406/429), so requests are spaced process-wide and a
    # refused one is retried once after ARXIV_RETRY_DELAY_SECONDS.
    ARXIV_MIN_INTERVAL_SECONDS: float = 3.0
    ARXIV_RETRY_DELAY_SECONDS: float = 5.0
    # Circuit breaker (RDA-067): observed in production that once arXiv
    # starts refusing requests, a single 5s-delayed retry is often not
    # enough -- and every one of a research's ~8 SEARCH queries hitting
    # arXiv again immediately just re-triggers the refusal, so the source
    # silently contributes zero results for the whole run with no visible
    # error. After ARXIV_BREAKER_FAILURE_THRESHOLD consecutive failed
    # .search() calls, stop calling arXiv entirely for
    # ARXIV_BREAKER_COOLDOWN_SECONDS so the other providers carry the run
    # and arXiv gets a real chance to recover instead of being hit again
    # every few seconds.
    ARXIV_BREAKER_FAILURE_THRESHOLD: int = 3
    ARXIV_BREAKER_COOLDOWN_SECONDS: float = 300.0

    # Europe PMC (RDA-066). No key.
    EUROPE_PMC_BASE_URL: str = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    EUROPE_PMC_TIMEOUT_SECONDS: float = 10.0

    # CORE (RDA-066). Requires a free API key (https://core.ac.uk/services/api).
    CORE_BASE_URL: str = "https://api.core.ac.uk/v3"
    CORE_API_KEY: str | None = None
    CORE_TIMEOUT_SECONDS: float = 10.0

    # Unpaywall enrichment (RDA-066). Requires a contact e-mail; disabled without one.
    UNPAYWALL_BASE_URL: str = "https://api.unpaywall.org/v2"
    UNPAYWALL_EMAIL: str | None = None
    UNPAYWALL_TIMEOUT_SECONDS: float = 8.0

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
    # Explicit, not read implicitly from the ambient OPENAI_BASE_URL env var
    # (RDA-067): that name is commonly set by unrelated tooling in the
    # shell/host environment, and the OpenAI SDK auto-picks it up when no
    # base_url is passed, which previously made embeddings silently target
    # whatever that ambient variable pointed at instead of the configured
    # local embedding backend -- with the relevance filter then failing
    # closed (no filtering, not an error) rather than raising.
    EMBEDDING_BASE_URL: str | None = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_BATCH_SIZE: int = 100

    # Retrieval (RDA-024). Default top-K and minimum cosine-similarity
    # threshold for DocumentRetriever; both can be overridden per-call.
    #
    # RETRIEVAL_MIN_SCORE was calibrated empirically in RDA-059 for the
    # production scenario, where the research question is in Portuguese and
    # the relevant academic documents are in English (cross-lingual). The
    # embedding model (text-embedding-3-small) is natively multilingual, but
    # cross-lingual cosine scores are systematically ~0.1 lower than
    # same-language scores. The RDA-058 value of 0.5, calibrated on an
    # English-only benchmark, sat above the relevant PT->EN cluster (p25
    # ~0.47) and dropped ~45% of relevant chunks (recall 0.55). The
    # cross-lingual threshold sweep shows 0.40 is the best operating point
    # (F1 0.62, recall 0.95, precision 0.46), and it also improves the
    # English-only benchmark (R@5 0.63 -> 0.80). For a RAG pipeline recall
    # matters more than precision: content not retrieved cannot be
    # synthesized, and the downstream evidence/claims stage filters noise.
    RETRIEVAL_TOP_K: int = 5
    RETRIEVAL_MIN_SCORE: float = 0.40

    # Document selection (RDA-058). Minimum cosine similarity between a
    # search result (title+abstract) and the research question for the result
    # to be selected for processing. Separates relevance from downloadability:
    # a result is only dropped for irrelevance below this score, never for
    # lacking a direct PDF. Calibrated conservatively so genuinely relevant
    # results are not filtered out.
    SELECTION_MIN_SCORE: float = 0.3

    # Pending-document backlog (RDA-067). A single orchestration run only
    # ever processes max_documents (RDA-034) of what a broad multi-source
    # search returns; the rest sit as "pending" until explicitly worked off.
    # This caps how many pending documents one process_pending_documents()
    # call downloads/extracts, so a single request stays bounded.
    PENDING_BATCH_DEFAULT_SIZE: int = 25

    # Retrieval query strategy (RDA-058). How the evidence node builds the
    # query passed to the retriever. "question" uses the research question
    # alone; "question_description" appends the EXTRACT task description.
    # Measured on the RDA-057 gold benchmark, "question" is the best
    # operating point (R@5 0.63, Hit@5 0.79, MRR 0.70) versus the old
    # generic task title (R@5 0.0) and question+description (R@5 0.57).
    RETRIEVAL_QUERY_STRATEGY: str = "question"

    # LLM (RDA-025). Completion model used by ClaimExtractor (and later
    # evidence/synthesis steps).
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str | None = None
    LLM_API_KEY: str | None = None

    # LLM (RDA-064). Per-request timeout for the OpenAI chat client, in
    # seconds. Without an explicit timeout the SDK defaults to 600s, so a
    # hung connection can block a request for 10 minutes. A bounded timeout
    # lets the caller fail fast and surface the error instead of stalling.
    LLM_TIMEOUT_SECONDS: float = 60.0

    # Synthesis (RDA-061). Minimum confidence level for a claim to be
    # included in the synthesized summary. Claims below this level are
    # excluded so unsupported statements are not presented as verified facts.
    # One of "HIGH", "MEDIUM" or "LOW".
    SYNTHESIS_MIN_CONFIDENCE: str = "MEDIUM"

    # Cost evaluation (RDA-050). Explicit per-model pricing in USD per 1k
    # tokens. Prices are estimates for cost reporting only, never billing.
    # Keep them here (config), not hardcoded, so they can be updated.
    LLM_PRICING: dict[str, dict[str, float]] = {
        "gpt-4": {"input": 0.03 / 1000, "output": 0.06 / 1000},
        "gpt-4o": {"input": 0.0025 / 1000, "output": 0.01 / 1000},
        "gpt-4o-mini": {"input": 0.00015 / 1000, "output": 0.0006 / 1000},
        "gpt-3.5-turbo": {"input": 0.0015 / 1000, "output": 0.002 / 1000},
    }

    # Cost evaluation (RDA-050). Per-search-call cost in USD per provider.
    # Free providers are 0.0 and are never charged.
    SEARCH_PRICING: dict[str, float] = {
        "openalex": 0.0,
        "crossref": 0.0,
        "arxiv": 0.0,
        "semantic_scholar": 0.0,
        "pubmed": 0.0,
        "europe_pmc": 0.0,
        "core": 0.0,
    }

    # Planning (RDA-030). Bounds for the number of tasks a plan may contain.
    PLANNING_MIN_TASKS: int = 3
    PLANNING_MAX_TASKS: int = 10

    @property
    def search_provider_names(self) -> list[str]:
        """Enabled search providers, in configured order (RDA-066)."""
        return [n.strip().lower() for n in self.SEARCH_PROVIDERS.split(",") if n.strip()]

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
