"""Test-session guards.

Tests must never run against the development database. ``.env.test`` points at a
dedicated ``*_test`` database; if that invariant is ever broken (e.g. someone
copies ``.env`` over ``.env.test``) fail fast instead of writing test data into
the dev database.
"""
import pytest

from app.config import settings


@pytest.fixture(scope="session", autouse=True)
def _require_test_database():
    if "_test" not in (settings.DATABASE_URL or ""):
        pytest.exit(
            "Refusing to run tests: DATABASE_URL does not point at a *_test "
            f"database ({settings.DATABASE_URL!r}). Point .env.test at a "
            "dedicated test database.",
            returncode=1,
        )
