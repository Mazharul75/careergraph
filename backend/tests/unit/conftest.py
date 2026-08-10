"""Fixtures for unit tests.

Unit tests must be hermetic: the same assertions have to hold on a laptop with a `.env` file, on
a CI runner that exports `ENVIRONMENT=ci`, and in a container with a dozen unrelated variables
set. Anything less produces tests that pass locally and fail in CI, which trains you to ignore
CI — the worst possible outcome for a pipeline.
"""

from __future__ import annotations

import pytest

# Every environment variable `Settings` reads. Keep in sync with app/core/config.py; a field
# added there but missed here becomes a test that quietly depends on the host environment.
SETTINGS_ENV_VARS = (
    "PROJECT_NAME",
    "API_V1_PREFIX",
    "ENVIRONMENT",
    "LOG_LEVEL",
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "REDIS_URL",
    "CORS_ORIGINS",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_ECHO",
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove application settings from the process environment for the duration of a test.

    `Settings(_env_file=None)` skips the .env *file* but still reads the process environment,
    which is where CI's `ENVIRONMENT=ci` comes from. Without this fixture, a test asserting the
    default value of a field passes locally and fails in CI — or worse, passes in both for the
    wrong reason.

    monkeypatch restores the original environment automatically at teardown.
    """
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
