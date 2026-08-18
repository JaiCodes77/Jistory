from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine
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
    from app.embeddings.factory import reset_embedding_provider

    reset_embedding_provider()


def _is_sqlite(conn: Connection) -> bool:
    return conn.dialect.name == "sqlite"


def _table_columns(conn: Connection, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _ensure_sqlite_columns(conn: Connection) -> None:
    """Add newly introduced columns on existing SQLite tables (create_all won't alter)."""
    if not _is_sqlite(conn):
        return

    alterations = {
        "import_jobs": [
            ("conversations_imported", "INTEGER"),
            ("messages_imported", "INTEGER"),
            ("conversations_skipped", "INTEGER"),
            ("chunks_indexed", "INTEGER"),
            ("index_error", "TEXT"),
        ],
        "ask_sessions": [
            ("title", "TEXT"),
            ("tagged_conversation_ids", "TEXT"),
        ],
        "memory_chunks": [
            ("source", "VARCHAR(64)"),
            ("timestamp", "DATETIME"),
            ("text", "TEXT"),
            ("message_ids", "TEXT"),
            ("embedding", "BLOB"),
            ("embedding_model", "VARCHAR(128)"),
        ],
    }

    for table, columns in alterations.items():
        existing = _table_columns(conn, table)
        if not existing:
            continue
        for name, col_type in columns:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))


def _ensure_unique_indexes(conn: Connection) -> None:
    """Create (source, external_id) uniqueness on existing databases without dropping data."""
    if not _is_sqlite(conn):
        return
    if not _table_columns(conn, "conversations"):
        return

    indexes = conn.execute(text("PRAGMA index_list(conversations)")).fetchall()
    names = {row[1] for row in indexes}
    if "uq_conversation_source_external" in names:
        return

    dupes = conn.execute(
        text(
            """
            SELECT source, external_id
            FROM conversations
            GROUP BY source, external_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    for source, external_id in dupes:
        columns = _table_columns(conn, "conversations")
        order_sql = "id DESC"
        if "updated_at" in columns or "created_at" in columns:
            order_sql = "COALESCE(updated_at, created_at) DESC, id DESC"
        ids = [
            row[0]
            for row in conn.execute(
                text(
                    f"""
                    SELECT id FROM conversations
                    WHERE source = :source AND external_id = :external_id
                    ORDER BY {order_sql}
                    """
                ),
                {"source": source, "external_id": external_id},
            ).fetchall()
        ]
        for conv_id in ids[1:]:
            if _table_columns(conn, "messages"):
                if "parent_message_id" in _table_columns(conn, "messages"):
                    conn.execute(
                        text("UPDATE messages SET parent_message_id = NULL WHERE conversation_id = :id"),
                        {"id": conv_id},
                    )
                conn.execute(text("DELETE FROM messages WHERE conversation_id = :id"), {"id": conv_id})
            if _table_columns(conn, "memory_chunks"):
                conn.execute(
                    text("DELETE FROM memory_chunks WHERE conversation_id = :id"),
                    {"id": conv_id},
                )
            conn.execute(text("DELETE FROM conversations WHERE id = :id"), {"id": conv_id})

    conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_source_external "
            "ON conversations (source, external_id)"
        )
    )


def _ensure_runtime_indexes(conn: Connection) -> None:
    if not _is_sqlite(conn):
        return
    columns = _table_columns(conn, "memory_chunks")
    if "timestamp" in columns:
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_chunks_timestamp ON memory_chunks (timestamp)")
        )


def ensure_runtime_schema(bind: Engine | Connection) -> None:
    """Additive SQLite upgrades used at startup and by Alembic.

    create_all remains the source of truth for new databases. This function
    never drops tables or the local jistory.db file.
    """
    if isinstance(bind, Engine):
        with bind.begin() as conn:
            _ensure_sqlite_columns(conn)
            _ensure_unique_indexes(conn)
            _ensure_runtime_indexes(conn)
        return
    _ensure_sqlite_columns(bind)
    _ensure_unique_indexes(bind)
    _ensure_runtime_indexes(bind)


def init_db() -> None:
    """Create data directory and initialize database tables."""
    from app.core.config import IMPORTS_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
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
