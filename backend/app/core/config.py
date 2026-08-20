"""Application configuration.

Every tunable value in the system enters through this module and nowhere else. No other file
calls ``os.environ`` directly, which means the full set of knobs is discoverable by reading one
class, and a missing or malformed value fails loudly at startup instead of at 3am inside a
request handler.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import (
    BeforeValidator,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# The value shipped in .env.example. Convenient locally, catastrophic in production — anyone
# who has read the repository can forge a token for any account. Rejected outright below.
DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-in-production"  # noqa: S105


def _split_csv(value: str | list[str]) -> list[str]:
    """Allow list-valued settings to be supplied as comma-separated environment variables.

    Environment variables are always strings, so ``CORS_ORIGINS=http://a,http://b`` needs to
    become ``["http://a", "http://b"]`` before Pydantic validates it as a list.
    """
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


# `NoDecode` is load-bearing. By default pydantic-settings treats any list-typed field coming
# from a .env file as JSON and calls json.loads() on it *before* validators run — so the
# perfectly reasonable `CORS_ORIGINS=http://localhost:3000` raises a parse error. NoDecode
# suppresses that step and hands the raw string to the BeforeValidator below.
CommaSeparatedList = Annotated[list[str], NoDecode, BeforeValidator(_split_csv)]


class Settings(BaseSettings):
    """Typed, validated application settings sourced from the environment."""

    model_config = SettingsConfigDict(
        # Two candidate locations, checked in order, with later files overriding earlier ones.
        # The repository root holds one `.env` shared by docker-compose and the application, so
        # there is a single place to edit; `backend/.env` is an optional per-developer override.
        # Missing files are ignored, which is what makes this work unchanged inside a container
        # where neither exists and configuration comes from the process environment.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Ignore unrelated variables rather than crashing — the process environment in a
        # container is full of things that have nothing to do with us.
        extra="ignore",
    )

    # --- Identity ------------------------------------------------------------------
    project_name: str = "CareerGraph"
    api_v1_prefix: str = "/api/v1"

    # `environment` is deliberately a Literal, not a plain str. A typo like ENVIRONMENT=prod
    # fails at startup instead of silently disabling production behaviour later.
    environment: Literal["local", "ci", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- Data stores ---------------------------------------------------------------
    # No default. If DATABASE_URL is absent the application refuses to start, which is
    # correct: an API that boots without a database only fails later and more confusingly.
    database_url: PostgresDsn
    test_database_url: PostgresDsn | None = None

    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")

    # --- HTTP ----------------------------------------------------------------------
    cors_origins: CommaSeparatedList = ["http://localhost:3000"]

    # --- Authentication ------------------------------------------------------------
    # SecretStr so the value renders as "**********" in logs, tracebacks, and repr(). A secret
    # leaks most often through an exception report, not through an attacker reading the code.
    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"

    # Short-lived by design. A JWT cannot be revoked before it expires, so its lifetime *is*
    # the window an attacker gets with a stolen one. Fifteen minutes keeps that window small
    # while refresh-token rotation keeps users signed in.
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # --- Database engine tuning ----------------------------------------------------
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # --- Background jobs -------------------------------------------------------------
    # Defaults to redis_url when unset, so local development needs one Redis variable, while
    # a deployment can point the broker somewhere else without moving the cache.
    celery_broker_url: RedisDsn | None = None

    # One worker process. The free instance has 512 MB shared with the API, and each extra
    # concurrent worker is another full Python interpreter plus whatever it loads.
    celery_concurrency: int = 1

    # Restart a worker process after this many tasks. Cheap insurance against a slow leak in a
    # parsing library turning into an OOM kill hours later.
    # One task per child process. Higher values amortise startup, but the embedding model is
    # ~200 MB resident (measured) and the free instance shares 512 MB with the API. Recycling
    # after every task is what actually returns that memory to the OS — CPython does not
    # reliably hand freed arenas back, and ONNX Runtime allocates natively. See ADR-0009.
    celery_max_tasks_per_child: int = 1

    # --- Rate limiting ---------------------------------------------------------------
    # Per-IP fixed windows on the unauthenticated credential endpoints (see ADR-0011).
    # The numbers are deliberately generous for humans and hopeless for brute force: nobody
    # mistypes a password ten times in five minutes, but an attacker needs millions of tries.
    rate_limit_enabled: bool = True
    rate_limit_login: int = 10
    rate_limit_login_window_seconds: int = 300
    # Registration is limited per hour: account flooding is a slow-burn abuse, not a burst.
    rate_limit_register: int = 20
    rate_limit_register_window_seconds: int = 3600
    # Refresh fires automatically from clients, so its ceiling is much higher — a legitimate
    # SPA refreshes once per access-token expiry, i.e. a few times an hour.
    rate_limit_refresh: int = 60
    rate_limit_refresh_window_seconds: int = 60

    # --- Observability ----------------------------------------------------------------
    # Error tracking is opt-in: unset means Sentry never initialises, which is the right
    # default for local development and CI where every induced test failure would be noise.
    sentry_dsn: str | None = None
    # 0.0 = error events only, no performance tracing. Tracing samples add volume against
    # Sentry's free quota and we have request logs for latency; errors are the scarce signal.
    sentry_traces_sample_rate: float = 0.0

    # --- Embeddings -------------------------------------------------------------------
    # The kill switch for the one component that can take the instance down. Set
    # EMBEDDING_ENABLED=false and scoring falls back to skill coverage alone -- degraded, but
    # every resume still parses and every score still explains itself. Turning a feature off
    # is a better outage than a container that dies on every upload.
    embedding_enabled: bool = True

    # --- Background maintenance -------------------------------------------------------
    # A resume still `pending` after this long has fallen through the crack between the
    # database commit and the queue write (see the dispatcher); the sweeper re-enqueues it.
    stuck_resume_after_minutes: int = 15

    # --- Uploads ---------------------------------------------------------------------
    # 5 MB. Resumes are a page or two; anything larger is a mistake or an attack, and an
    # unbounded upload is a trivial way to exhaust memory and disk.
    max_upload_bytes: int = 5 * 1024 * 1024

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """The same database, addressed with a synchronous driver.

        Celery workers have no event loop, so they cannot use the asyncpg engine (ADR-0005).
        Deriving this from ``database_url`` rather than adding a second setting means the two
        can never drift apart and point at different databases — a failure that would be
        invisible until data mysteriously failed to appear.
        """
        return str(self.database_url).replace("+asyncpg", "+psycopg", 1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def broker_url(self) -> str:
        return str(self.celery_broker_url or self.redis_url)

    @model_validator(mode="after")
    def _reject_weak_secret_outside_development(self) -> Settings:
        """Fail startup rather than run production on a publicly known signing key.

        The check runs at boot, so a misconfigured deploy crashes immediately and visibly
        instead of serving traffic that anyone can forge tokens against.
        """
        if self.environment in ("staging", "production"):
            secret = self.jwt_secret_key.get_secret_value()
            if secret == DEV_JWT_SECRET:
                raise ValueError(
                    "JWT_SECRET_KEY is still the development placeholder. Generate one with: "
                    'python -c "import secrets; print(secrets.token_urlsafe(64))"'
                )
            # 32 bytes is the output size of HMAC-SHA256; a key shorter than that reduces the
            # effective security of the signature.
            if len(secret) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters.")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def docs_url(self) -> str | None:
        """Swagger UI path, or ``None`` to disable it.

        Interactive API docs are useful everywhere except production, where they advertise
        the full surface area of the API to anyone who asks.
        """
        return None if self.is_production else "/docs"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached because reading and validating the environment on every request would be wasteful,
    and because a single instance means configuration cannot drift between callers. Tests
    clear the cache via ``get_settings.cache_clear()`` when they need to override values.
    """
    return Settings()  # type: ignore[call-arg]  # values come from env, not from kwargs
