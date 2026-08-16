"""SQLite FTS5 index for message content and conversation titles."""

from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

logger = logging.getLogger("jistory.fts")

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_FTS_RESERVED = frozenset({"AND", "OR", "NOT", "NEAR", "MATCH"})


def ensure_fts(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    content,
                    title,
                    source,
                    conversation_id UNINDEXED,
                    message_id UNINDEXED,
                    created_at UNINDEXED,
                    tokenize = 'porter unicode61 remove_diacritics 1'
                )
                """
            )
        )
        conn.execute(text("DROP TRIGGER IF EXISTS messages_ai"))
        conn.execute(text("DROP TRIGGER IF EXISTS messages_ad"))
        conn.execute(text("DROP TRIGGER IF EXISTS messages_au"))
        conn.execute(
            text(
                """
                CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(
                        rowid, content, title, source, conversation_id, message_id, created_at
                    )
                    SELECT
                        new.rowid,
                        new.content,
                        COALESCE(c.title, ''),
                        COALESCE(c.source, ''),
                        new.conversation_id,
                        new.id,
                        COALESCE(new.created_at, '')
                    FROM conversations c
                    WHERE c.id = new.conversation_id;
                END
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
                    DELETE FROM messages_fts WHERE rowid = old.rowid;
                END
                """
            )
        )


        fts_count = conn.execute(text("SELECT COUNT(*) FROM messages_fts")).scalar() or 0
        message_count = conn.execute(text("SELECT COUNT(*) FROM messages")).scalar() or 0
        if message_count > 0 and fts_count == 0:
            logger.info("Rebuilding FTS index for %s messages", message_count)
            conn.execute(
                text(
                    """
                    INSERT INTO messages_fts(
                        rowid, content, title, source, conversation_id, message_id, created_at
                    )
                    SELECT
                        m.rowid,
                        m.content,
                        COALESCE(c.title, ''),
                        COALESCE(c.source, ''),
                        m.conversation_id,
                        m.id,
                        COALESCE(m.created_at, '')
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    """
                )
            )


def sanitize_fts_query(raw: str) -> str | None:
    """Turn user text into a safe FTS5 MATCH query. Returns None if empty."""
    tokens = [tok for tok in _TOKEN_RE.findall(raw) if tok.upper() not in _FTS_RESERVED]
    if not tokens:
        return None
    # Prefix match on each token for partial keywords (e.g. grafana, FastAPI).
    return " AND ".join(f"{tok}*" for tok in tokens[:12])


def sanitize_fts_query_or(raw: str) -> str | None:
    tokens = [tok for tok in _TOKEN_RE.findall(raw) if tok.upper() not in _FTS_RESERVED]
    if not tokens:
        return None
    return " OR ".join(f"{tok}*" for tok in tokens[:12])


def fts_available(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1 FROM messages_fts LIMIT 1"))
        return True
    except Exception:
        return False
