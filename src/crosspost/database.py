"""Database engine creation, session management, and table initialization."""

from contextlib import contextmanager
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.engine import Engine


def get_engine(database_url: str) -> Engine:
    """Create and return a SQLAlchemy engine for the given database URL.

    Args:
        database_url: SQLAlchemy-compatible database URL (e.g., "sqlite:///crosspost.db")

    Returns:
        Configured Engine instance with echo disabled.
    """
    return create_engine(database_url, echo=False)


def init_db(engine: Engine) -> None:
    """Create all tables defined in SQLModel metadata.

    This is idempotent — safe to call on an existing database.

    Args:
        engine: SQLAlchemy engine to create tables on.
    """
    # Import models to register them with SQLModel metadata before creating tables
    from crosspost import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session(engine: Engine) -> Generator[Session, None, None]:
    """Context manager that yields a SQLModel Session.

    The session is automatically closed when the context exits.
    Callers are responsible for committing or rolling back transactions.

    Args:
        engine: SQLAlchemy engine to create the session on.

    Yields:
        A SQLModel Session instance.
    """
    with Session(engine) as session:
        yield session
