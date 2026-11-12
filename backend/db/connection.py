"""SQLite by default. Postgres is supported only through a SELECT-only login."""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from backend.config import DB_PATH, get_settings

_reader: Engine | None = None
_writer: Engine | None = None


def sqlite_reader_url(path=DB_PATH) -> str:
    return "sqlite:///file:" + path.resolve().as_posix() + "?mode=ro&uri=true"


def get_writer_engine() -> Engine:
    global _writer
    settings = get_settings()
    if not settings.use_sqlite:
        raise RuntimeError("Refusing to open a writable connection to an external database.")
    if _writer is None:
        _writer = create_engine(
            f"sqlite:///{DB_PATH.resolve().as_posix()}",
            poolclass=NullPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_writer, "connect")
        def _writer_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.close()

    return _writer


def get_reader_engine() -> Engine:
    global _reader
    if _reader is None:
        settings = get_settings()
        if settings.use_sqlite:
            engine = create_engine(
                sqlite_reader_url(),
                poolclass=NullPool,
                connect_args={"check_same_thread": False},
            )
        else:
            engine = create_engine(settings.db_connection_string, pool_pre_ping=True)
        _install_reader_guard(engine)
        _reader = engine
    return _reader


def _install_reader_guard(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        try:
            if engine.dialect.name == "sqlite":
                cursor.execute("PRAGMA query_only = ON")
                cursor.execute("PRAGMA busy_timeout = 5000")
            elif engine.dialect.name == "postgresql":
                cursor.execute("SET default_transaction_read_only = ON")
                cursor.execute("SET statement_timeout = '15s'")
        finally:
            cursor.close()


def reset_engines() -> None:
    global _reader, _writer
    if _reader is not None:
        _reader.dispose()
    if _writer is not None:
        _writer.dispose()
    _reader = None
    _writer = None


def sql_dialect() -> str:
    if get_settings().use_sqlite:
        return "SQLite"
    return "PostgreSQL"
