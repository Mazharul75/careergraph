"""Fixtures for unit tests.

Unit tests must be hermetic: the same assertions have to hold on a laptop with a `.env` file, on
a CI runner that exports `ENVIRONMENT=ci` and `JWT_SECRET_KEY=...`, and in a container with a
dozen unrelated variables set. Anything less produces tests that pass locally and fail in CI,
which trains you to ignore CI — the worst possible outcome for a pipeline.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import Settings, get_settings

# Derived from the model rather than hand-listed.
#
# An earlier version of this file enumerated the variables manually. Four settings were then
# added to `Settings` and not mirrored here, so `test_missing_secret_is_fatal` silently began
# reading JWT_SECRET_KEY from the CI runner's environment and stopped testing anything — it
# passed locally and failed in CI. Deriving the list means adding a setting can never leave a
# test depending on the host environment again.
#
# `Settings` uses no env_prefix and is case-insensitive, so the variable name for each field is
# simply its uppercased name. Computed properties are absent from `model_fields`, which is
# correct: they are derived, not configured.
SETTINGS_ENV_VARS = tuple(name.upper() for name in Settings.model_fields)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make `Settings()` hermetic for the duration of a test — no process environment, no
    `.env` file on disk.

    Two separate sources have to be neutralised, not one. Stripping process environment
    variables handles a CI runner's or a container's exports, but pydantic-settings reads
    `../.env` and `.env` **directly off disk**, entirely independent of `os.environ` — so a
    developer's own real `.env` file (a Google OAuth client id set for local testing, a real
    Sentry DSN, anything optional) leaks into every test that asserts a field is absent by
    default, regardless of what monkeypatch does to the process environment. This bit a real
    test the day `GOOGLE_CLIENT_ID` was first added to a contributor's own `.env`.

    Setting `env_file=None` on the class for the duration of the test closes that second path;
    `monkeypatch.setattr` restores the original `model_config` automatically at teardown.
    monkeypatch's own environment stripping still runs too, for the process-environment case
    a container or CI runner represents.
    """
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    # A cached Settings built under this test's neutralised model_config must not survive to
    # be read by whatever runs next, after monkeypatch has restored the real env_file.
    get_settings.cache_clear()
