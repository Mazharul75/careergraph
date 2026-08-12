"""Configuration parsing and validation.

Pure unit tests: no database, no HTTP, no filesystem beyond the environment.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import DEV_JWT_SECRET, Settings

_VALID_DSN = "postgresql+asyncpg://user:pass@localhost:5432/careergraph"
_STRONG_SECRET = "x" * 64


def _settings(**overrides: object) -> Settings:
    """Build Settings from explicit values, ignoring any .env file on disk.

    Without `_env_file=None`, these tests would pass or fail depending on whether the
    developer happens to have a .env present — the definition of a flaky test.
    """
    values: dict[str, object] = {
        "database_url": _VALID_DSN,
        "jwt_secret_key": _STRONG_SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class TestDatabaseUrl:
    def test_missing_database_url_is_fatal(self) -> None:
        # An API that boots without a database only fails later, and more confusingly.
        # The autouse `isolated_environment` fixture strips DATABASE_URL from the process
        # environment, so this genuinely exercises the missing-value path.
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_malformed_url_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _settings(database_url="not-a-database-url")


class TestEnvironment:
    def test_defaults_to_local(self) -> None:
        assert _settings().environment == "local"

    def test_typo_in_environment_is_rejected(self) -> None:
        # "prod" is not "production". Catching this at startup is the entire point of using a
        # Literal here instead of str.
        with pytest.raises(ValidationError):
            _settings(environment="prod")

    @pytest.mark.parametrize("env", ["local", "ci", "staging", "production"])
    def test_accepts_known_environments(self, env: str) -> None:
        assert _settings(environment=env).environment == env


class TestCorsOrigins:
    def test_parses_comma_separated_string(self) -> None:
        settings = _settings(cors_origins="http://a.test,http://b.test")
        assert settings.cors_origins == ["http://a.test", "http://b.test"]

    def test_strips_whitespace_and_drops_empty_entries(self) -> None:
        settings = _settings(cors_origins=" http://a.test , , http://b.test ")
        assert settings.cors_origins == ["http://a.test", "http://b.test"]

    def test_accepts_a_real_list(self) -> None:
        settings = _settings(cors_origins=["http://a.test"])
        assert settings.cors_origins == ["http://a.test"]


class TestJwtSecret:
    def test_missing_secret_is_fatal(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, database_url=_VALID_DSN)  # type: ignore[call-arg]

    def test_secret_is_masked_in_repr(self) -> None:
        # SecretStr matters because secrets leak through exception reports far more often than
        # through someone reading source code.
        assert _STRONG_SECRET not in repr(_settings())
        assert _STRONG_SECRET not in str(_settings())

    def test_secret_value_is_still_retrievable(self) -> None:
        assert _settings().jwt_secret_key.get_secret_value() == _STRONG_SECRET

    def test_development_placeholder_is_fine_locally(self) -> None:
        assert _settings(environment="local", jwt_secret_key=DEV_JWT_SECRET) is not None

    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_development_placeholder_is_refused_in_deployed_environments(self, env: str) -> None:
        # The placeholder is published in this repository. Booting production with it would let
        # anyone who has read the repo forge a token for any account.
        with pytest.raises(ValidationError, match="development placeholder"):
            _settings(environment=env, jwt_secret_key=DEV_JWT_SECRET)

    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_short_secret_is_refused_in_deployed_environments(self, env: str) -> None:
        with pytest.raises(ValidationError, match="at least 32 characters"):
            _settings(environment=env, jwt_secret_key="too-short")

    def test_short_secret_is_tolerated_locally(self) -> None:
        # Local development should not be obstructed by production-grade requirements.
        assert _settings(environment="local", jwt_secret_key="short") is not None


class TestTokenLifetimes:
    def test_access_tokens_default_to_fifteen_minutes(self) -> None:
        assert _settings().access_token_expire_minutes == 15

    def test_refresh_tokens_default_to_thirty_days(self) -> None:
        assert _settings().refresh_token_expire_days == 30


class TestDerivedFlags:
    def test_is_production_only_in_production(self) -> None:
        assert _settings(environment="production").is_production is True
        assert _settings(environment="staging").is_production is False

    def test_docs_are_disabled_in_production(self) -> None:
        # Swagger UI publicly advertises the full API surface. Fine locally, not in production.
        assert _settings(environment="production").docs_url is None
        assert _settings(environment="local").docs_url == "/docs"
