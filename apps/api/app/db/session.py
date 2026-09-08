"""Engine/session factory for Postgres-backed persistence (Milestone F5).

Engines are expensive to construct (connection pool setup) and must be
shared across requests, not rebuilt per call — the exact same "load once,
cache, reuse" discipline `app/api/deps.py` already applies to the F4
model singletons, applied here to database engines. Keyed by
`DATABASE_URL` (rather than a single unconditional global) so tests that
each construct their own isolated `Settings(DATABASE_URL=...)` — see
`tests/conftest.py` — never share state with the production engine or
with each other.
"""

import threading
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.models import Base

_engines: dict[str, Engine] = {}
_session_factories: dict[str, sessionmaker[Session]] = {}
_lock = threading.Lock()


def _build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        # SQLite-specific settings so a single `sqlite:///:memory:` (or a
        # shared-cache file) URL behaves like one real database across
        # multiple connections/threads within one test — the default
        # SQLite behavior (a fresh, empty in-memory database per
        # connection, and same-thread-only connections) would otherwise
        # make an in-memory test database invisible to any connection but
        # the one that created it.
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(
        database_url,
        pool_pre_ping=True,
        # Never hang indefinitely if Postgres is unreachable (a firewall
        # silently dropping packets, a not-yet-started container, ...) —
        # `GET /ready` and every repository call must fail fast and
        # honestly rather than block the caller forever. 5s is generous
        # for a healthy local/Docker-network connection.
        connect_args={"connect_timeout": 5},
    )


def get_engine(settings: Settings) -> Engine:
    """The process-wide engine for `settings.DATABASE_URL`, created once."""
    database_url = settings.DATABASE_URL
    engine = _engines.get(database_url)
    if engine is not None:
        return engine
    with _lock:
        engine = _engines.get(database_url)
        if engine is None:
            engine = _build_engine(database_url)
            _engines[database_url] = engine
    return engine


def get_session_factory(settings: Settings) -> sessionmaker[Session]:
    database_url = settings.DATABASE_URL
    factory = _session_factories.get(database_url)
    if factory is not None:
        return factory
    with _lock:
        factory = _session_factories.get(database_url)
        if factory is None:
            factory = sessionmaker(bind=get_engine(settings), expire_on_commit=False)
            _session_factories[database_url] = factory
    return factory


def create_all_tables(settings: Settings) -> None:
    """Create every table directly from the ORM metadata — used by tests
    (isolated SQLite databases) and by scripts that don't want to run the
    full Alembic migration chain. Production deployments use `alembic
    upgrade head` (see `apps/api/alembic/`), never this function."""
    Base.metadata.create_all(get_engine(settings))


def get_db_session(settings: Settings) -> Iterator[Session]:
    """FastAPI/worker dependency: yields one `Session` per call, always
    closed afterward — never a session shared/leaked across requests."""
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
    finally:
        session.close()
