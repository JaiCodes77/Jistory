from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DATA_DIR, get_settings
from app.db.base import Base
from app.db.fts import ensure_fts

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _attach_sqlite_pragma(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ARG001
        settings = get_settings()
        if settings.database_url.startswith("sqlite"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        _engine = create_engine(settings.database_url, connect_args=connect_args, echo=False)
        _attach_sqlite_pragma(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def reset_engine() -> None:
    """Dispose the process-wide engine. Used by tests when DATABASE_URL changes."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def _ensure_sqlite_columns(engine: Engine) -> None:
    """Add newly introduced columns on existing SQLite tables (create_all won't alter)."""
    settings = get_settings()
    if not settings.database_url.startswith("sqlite"):
        return

    alterations = {
        "import_jobs": [
            ("conversations_imported", "INTEGER"),
            ("messages_imported", "INTEGER"),
            ("conversations_skipped", "INTEGER"),
        ]
    }

    with engine.begin() as conn:
        for table, columns in alterations.items():
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            if not existing:
                continue
            for name, col_type in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))


def init_db() -> None:
    """Create data directory and initialize database tables."""
    from app.core.config import IMPORTS_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns(engine)
    try:
        ensure_fts(engine)
    except Exception:
        logger = __import__("logging").getLogger("jistory.db")
        logger.exception("FTS5 is unavailable; keyword search will be limited")


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
