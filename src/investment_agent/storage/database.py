from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from investment_agent.config import Settings, get_settings


def make_engine(settings: Settings | None = None) -> Engine:
    resolved = settings or get_settings()
    connect_args: dict[str, object] = {}
    if resolved.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(resolved.database_url, future=True, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session],
) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
