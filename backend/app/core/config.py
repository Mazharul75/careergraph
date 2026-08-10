"""Application configuration.

Every tunable value in the system enters through this module and nowhere else. No other file
calls ``os.environ`` directly, which means the full set of knobs is discoverable by reading one
class, and a missing or malformed value fails loudly at startup instead of at 3am inside a
request handler.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BeforeValidator, PostgresDsn, RedisDsn, computed_field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # --- Database engine tuning ----------------------------------------------------
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

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
