import os
from typing import Iterator, List

import pytest
from redis import Redis

from redisgraph import GraphManager


def _env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@pytest.fixture(scope="session")
def redis_backend_info(pytestconfig: pytest.Config) -> dict:
    """Choose which Redis backend to use for the entire test session.

    Returns a dict with keys:
      - kind: "real" | "fakeredis"
      - host, port, db
    """

    use_real = _env_flag("GRAPH_TEST_USE_REAL_REDIS", default=False)
    db = 0

    if use_real:
        host = os.getenv("GRAPH_TEST_REDIS_HOST", "localhost")
        port_raw = os.getenv("GRAPH_TEST_REDIS_PORT", "6379")
        try:
            port = int(port_raw)
        except ValueError as e:
            raise ValueError(f"GRAPH_TEST_REDIS_PORT must be an integer, got: {port_raw!r}") from e

        return {"kind": "real", "host": host, "port": port, "db": db}

    return {"kind": "fakeredis", "host": "localhost", "port": 6379, "db": db}


def pytest_report_header(config: pytest.Config) -> List[str]:
    """Add the backend banner to pytest's header (printed once per invocation)."""

    # If running under xdist, only the master should add session header lines.
    if hasattr(config, "workerinput"):
        return []

    use_real = _env_flag("GRAPH_TEST_USE_REAL_REDIS", default=False)
    if use_real:
        host = os.getenv("GRAPH_TEST_REDIS_HOST", "localhost")
        port = os.getenv("GRAPH_TEST_REDIS_PORT", "6379")
        return [f"[redisgraph tests] redis backend: real ({host}:{port}, db=0)"]

    return ["[redisgraph tests] redis backend: fakeredis (in-memory, db=0)"]


@pytest.fixture
def redis_client(redis_backend_info: dict) -> Iterator[Redis]:
    """
    Provides a Redis client instance for use in tests.

    Default:
        Uses an in-memory fakeredis instance so tests don't require a running Redis.

    Real Redis mode:
                Set GRAPH_TEST_USE_REAL_REDIS=1 to use a real Redis server.
        You can override connection details with:
                    - GRAPH_TEST_REDIS_HOST (default: localhost)
                    - GRAPH_TEST_REDIS_PORT (default: 6379)

    Note:
        db=0 and decode_responses=True are intentionally fixed for the test suite.

        The test suite is designed to clean up only the keys it creates (scoped by
        the GraphManager's key patterns). We intentionally do NOT flush the
        entire Redis database.
    """

    if redis_backend_info["kind"] == "real":
        rc = Redis(
            host=redis_backend_info["host"],
            port=redis_backend_info["port"],
            db=redis_backend_info["db"],
            decode_responses=True,
        )
    else:
        try:
            import fakeredis  # type: ignore
        except ImportError as e:
            raise ImportError(
                "fakeredis is required to run tests without a real Redis server. "
                "Install test extras (e.g. `pip install -e .[test]`) or set GRAPH_TEST_USE_REAL_REDIS=1."
            ) from e

        # fakeredis mimics redis-py and supports decode_responses.
        rc = fakeredis.FakeRedis(db=redis_backend_info["db"], decode_responses=True)

    yield rc

    rc.close()


@pytest.fixture
def graph_manager(redis_client: Redis) -> Iterator[GraphManager]:
    """
    Provides a GraphManager instance using the Redis client fixture.

    Yields a GraphManager configured for test usage.
    """

    yield GraphManager(redis_client)
