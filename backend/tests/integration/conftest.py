"""Fixtures for integration tests.

Migrations are applied here rather than in the root conftest so that **unit tests need no
database at all**. Previously the migration fixture was session-scoped and autouse, which meant
running a single pure-function test required Docker to be up — slow, and a strong disincentive
to running tests at all.

Now `pytest tests/unit` works offline in under a second, and only this directory pays for a
live database.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _migrated_database(apply_migrations: None) -> None:
    """Bring the test database to head before any integration test runs.

    Autouse within this package only. Tests that reach the database through the synchronous
    worker session (test_parse_task.py) never touch the `engine` fixture, so they would
    otherwise run against an unmigrated schema.
    """
