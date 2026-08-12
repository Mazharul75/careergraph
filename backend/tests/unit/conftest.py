"""Fixtures for unit tests.

Unit tests must be hermetic: the same assertions have to hold on a laptop with a `.env` file, on
a CI runner that exports `ENVIRONMENT=ci` and `JWT_SECRET_KEY=...`, and in a container with a
dozen unrelated variables set. Anything less produces tests that pass locally and fail in CI,
which trains you to ignore CI — the worst possible outcome for a pipeline.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings

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
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove application settings from the process environment for the duration of a test.

    `Settings(_env_file=None)` skips the .env *file* but still reads the process environment.
    Without this fixture, a test asserting a field's default value passes locally and fails in
    CI — or worse, passes in both for the wrong reason.

    monkeypatch restores the original environment automatically at teardown, and test modules
    that need a specific value (a JWT signing key, say) set it in their own fixture, which runs
    after this one.
    """
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
