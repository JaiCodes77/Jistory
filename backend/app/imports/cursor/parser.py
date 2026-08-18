"""Parse Cursor local composer/chat transcripts into ParsedConversation rows.

Cursor storage changes across versions. This importer only reads files the user
points at — it never scans $HOME or ~/Library by default.

Observed layouts (not exhaustive):

* SQLite `state.vscdb` with `cursorDiskKV` and/or `ItemTable` key/value rows.
  - `composerData:{composerId}` — session metadata. `fullConversationHeadersOnly`
    lists bubble ids in order (`type` 1=user, 2=assistant).
  - `bubbleId:{composerId}:{bubbleId}` — one message. `text` is the body;
    `toolFormerData` / empty text is treated as tool noise.
  - Older blobs embed `conversationMap` inside `composerData`.
  - `composer.composerHeaders` / `composer.composerData` in ItemTable are indexes.
* A folder of `.json` / `.jsonl` transcripts with `messages` / `bubbles`.

Public Cursor share URLs are not imported (fail closed).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.imports.parsers.base import ParsedConversation, ParsedMessage, ParseResult

logger = logging.getLogger("jistory.cursor")

BUBBLE_USER = 1
BUBBLE_ASSISTANT = 2


def parse_cursor_import(import_dir: Path) -> ParseResult:
    conversations: list[ParsedConversation] = []
    skipped = 0
    warnings: list[str] = []

    sqlite_files = sorted(
        path
        for path in import_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".vscdb", ".sqlite", ".db"}
    )
    if not sqlite_files:
        sqlite_files = sorted(import_dir.glob("*.vscdb"))

    for db_path in sqlite_files:
        try:
            parsed, skip, warn = _parse_vscdb(db_path)
        except Exception:
            logger.exception("Failed to parse Cursor database")
            warnings.append("A Cursor database file could not be parsed.")
            skipped += 1
            continue
        conversations.extend(parsed)
        skipped += skip
        warnings.extend(warn)

    for text_path in sorted(import_dir.iterdir()):
        if not text_path.is_file():
            continue
        if text_path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        try:
            parsed, skip, warn = _parse_transcript_file(text_path)
        except Exception:
            logger.exception("Failed to parse Cursor transcript file")
            warnings.append("A Cursor transcript file could not be parsed.")
            skipped += 1
            continue
        conversations.extend(parsed)
        skipped += skip
        warnings.extend(warn)

    by_id: dict[str, ParsedConversation] = {}
    for convo in conversations:
        by_id[convo.external_id] = convo

    logger.info(
        "Parsed Cursor conversations=%d skipped=%d files=%d",
        len(by_id),
        skipped,
        len(sqlite_files),
    )
    return ParseResult(conversations=list(by_id.values()), skipped=skipped, warnings=warnings)


def _parse_vscdb(path: Path) -> tuple[list[ParsedConversation], int, list[str]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        kv = _load_relevant_kv(conn)
    finally:
        conn.close()

    composers = _composer_payloads(kv)
    conversations: list[ParsedConversation] = []
    skipped = 0
    for composer_id, payload in composers.items():
        parsed = _conversation_from_composer(composer_id, payload, kv)
        if parsed is None:
            skipped += 1
            continue
        conversations.append(parsed)
    return conversations, skipped, []


def _load_relevant_kv(conn: sqlite3.Connection) -> dict[str, Any]:
    kv: dict[str, Any] = {}
    tables = _existing_tables(conn)
    for table in ("cursorDiskKV", "ItemTable"):
        if table not in tables:
            continue
        try:
            rows = conn.execute(
                f"""
                SELECT key, value FROM {table}
                WHERE key LIKE 'composerData:%'
                   OR key LIKE 'bubbleId:%'
                   OR key IN ('composer.composerData', 'composer.composerHeaders')
                """
            )
        except sqlite3.Error:
            continue
        for row in rows:
            key = str(row["key"] if isinstance(row, sqlite3.Row) else row[0])
            raw = row["value"] if isinstance(row, sqlite3.Row) else row[1]
            parsed = _decode_json(raw)
            if parsed is not None:
                kv[key] = parsed
    return kv


def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _decode_json(raw: Any) -> Any | None:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _composer_payloads(kv: dict[str, Any]) -> dict[str, dict[str, Any]]:
    composers: dict[str, dict[str, Any]] = {}
    for key, value in kv.items():
        if key.startswith("composerData:") and isinstance(value, dict):
            composer_id = key.split(":", 1)[1].strip()
            if composer_id:
                composers[composer_id] = value

    for index_key in ("composer.composerHeaders", "composer.composerData"):
        index = kv.get(index_key)
        all_composers = []
        if isinstance(index, dict):
            all_composers = index.get("allComposers") or index.get("composers") or []
        if isinstance(all_composers, list):
            for item in all_composers:
                if not isinstance(item, dict):
                    continue
                composer_id = str(item.get("composerId") or item.get("id") or "").strip()
                if not composer_id:
                    continue
                existing = composers.get(composer_id, {})
                merged = {**item, **existing}
                composers[composer_id] = merged
    return composers


def _conversation_from_composer(
    composer_id: str,
    payload: dict[str, Any],
    kv: dict[str, Any],
) -> ParsedConversation | None:
    headers = payload.get("fullConversationHeadersOnly") or payload.get("headers") or []
    conversation_map = payload.get("conversationMap") if isinstance(payload.get("conversationMap"), dict) else {}
    bubbles: list[tuple[str, dict[str, Any]]] = []

    if isinstance(headers, list) and headers:
        for header in headers:
            if not isinstance(header, dict):
                continue
            bubble_id = str(header.get("bubbleId") or header.get("id") or "").strip()
            if not bubble_id:
                continue
            blob = kv.get(f"bubbleId:{composer_id}:{bubble_id}")
            if not isinstance(blob, dict):
                mapped = conversation_map.get(bubble_id)
                blob = mapped if isinstance(mapped, dict) else dict(header)
            else:
                blob = {**header, **blob}
            bubbles.append((bubble_id, blob))
    elif conversation_map:
        for bubble_id, blob in conversation_map.items():
            if isinstance(blob, dict):
                bubbles.append((str(bubble_id), blob))

    messages: list[ParsedMessage] = []
    parent: str | None = None
    for index, (bubble_id, blob) in enumerate(bubbles):
        role = _bubble_role(blob)
        text = _bubble_text(blob)
        if role == "tool" and not text:
            continue
        if not text:
            continue
        created = _timestamp(blob.get("createdAt") or blob.get("timestamp") or payload.get("createdAt"))
        messages.append(
            ParsedMessage(
                external_id=bubble_id,
                parent_external_id=parent,
                role=role,
                content=text,
                created_at=created,
                sequence_number=index,
            )
        )
        parent = bubble_id

    usable = [msg for msg in messages if msg.role in {"user", "assistant"}]
    if not usable:
        return None

    title = (
        str(payload.get("name") or payload.get("title") or "").strip()
        or None
    )
    created_at = _timestamp(payload.get("createdAt") or payload.get("created_at"))
    updated_at = _timestamp(payload.get("lastUpdatedAt") or payload.get("updatedAt"))
    return ParsedConversation(
        external_id=composer_id,
        title=title,
        created_at=created_at,
        updated_at=updated_at or created_at,
        messages=messages,
    )


def _bubble_role(blob: dict[str, Any]) -> str:
    if blob.get("toolFormerData") or blob.get("tool_former_data"):
        return "tool"
    raw_type = blob.get("type")
    if raw_type == BUBBLE_USER or raw_type == "user" or raw_type == "human":
        return "user"
    if raw_type == BUBBLE_ASSISTANT or raw_type in {"assistant", "ai", "model"}:
        return "assistant"
    role = str(blob.get("role") or blob.get("sender") or "").strip().lower()
    if role in {"user", "human"}:
        return "user"
    if role in {"assistant", "ai", "model"}:
        return "assistant"
    if role in {"tool", "function"}:
        return "tool"
    if raw_type == 3:
        return "tool"
    return "assistant"


def _bubble_text(blob: dict[str, Any]) -> str:
    for key in ("text", "richText", "content"):
        value = blob.get(key)
        extracted = _stringify_content(value)
        if extracted:
            return extracted
    parts = blob.get("parts")
    if isinstance(parts, list):
        bits = [_stringify_content(part) for part in parts]
        return "\n".join(bit for bit in bits if bit).strip()
    return ""


def _stringify_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        bits = [_stringify_content(item) for item in value]
        return "\n".join(bit for bit in bits if bit).strip()
    if isinstance(value, dict):
        if value.get("text"):
            return str(value.get("text") or "").strip()
        if value.get("type") == "text":
            return str(value.get("text") or "").strip()
    return ""


def _timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 1_000_000_000_000:
            number /= 1000.0
        try:
            return datetime.fromtimestamp(number, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _parse_transcript_file(path: Path) -> tuple[list[ParsedConversation], int, list[str]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        conversations: list[ParsedConversation] = []
        skipped = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            parsed = _conversation_from_transcript(payload, fallback_id=path.stem)
            if parsed is None:
                skipped += 1
            else:
                conversations.append(parsed)
        return conversations, skipped, []

    payload = json.loads(text)
    if isinstance(payload, list):
        conversations = []
        skipped = 0
        for index, item in enumerate(payload):
            parsed = _conversation_from_transcript(item, fallback_id=f"{path.stem}-{index}")
            if parsed is None:
                skipped += 1
            else:
                conversations.append(parsed)
        return conversations, skipped, []
    parsed = _conversation_from_transcript(payload, fallback_id=path.stem)
    if parsed is None:
        return [], 1, []
    return [parsed], 0, []


def _conversation_from_transcript(payload: Any, *, fallback_id: str) -> ParsedConversation | None:
    if not isinstance(payload, dict):
        return None
    external_id = str(
        payload.get("composerId")
        or payload.get("id")
        or payload.get("conversation_id")
        or fallback_id
    ).strip()
    if not external_id:
        return None
    raw_messages = payload.get("messages") or payload.get("bubbles") or payload.get("chat_messages") or []
    if not isinstance(raw_messages, list):
        return None
    messages: list[ParsedMessage] = []
    parent: str | None = None
    for index, item in enumerate(raw_messages):
        if not isinstance(item, dict):
            continue
        role = _bubble_role(item)
        text = _bubble_text(item)
        if role == "tool" and not text:
            continue
        if not text:
            continue
        msg_id = str(item.get("id") or item.get("bubbleId") or f"{external_id}-{index}")
        messages.append(
            ParsedMessage(
                external_id=msg_id,
                parent_external_id=parent,
                role=role,
                content=text,
                created_at=_timestamp(item.get("createdAt") or item.get("created_at")),
                sequence_number=index,
            )
        )
        parent = msg_id
    if not any(msg.role in {"user", "assistant"} for msg in messages):
        return None
    title = str(payload.get("title") or payload.get("name") or "").strip() or None
    return ParsedConversation(
        external_id=external_id,
        title=title,
        created_at=_timestamp(payload.get("createdAt") or payload.get("created_at")),
        updated_at=_timestamp(payload.get("updatedAt") or payload.get("updated_at")),
        messages=messages,
    )
