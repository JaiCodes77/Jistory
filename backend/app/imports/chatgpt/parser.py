"""Parse ChatGPT conversations.json into normalized dataclasses."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.imports.chatgpt.content import extract_message_text, normalize_role
from app.imports.parsers.base import ParsedConversation, ParsedMessage, ParseResult
from app.imports.validators import is_chatgpt_conversation_file

logger = logging.getLogger("jistory.parser")


def find_conversation_files(import_dir: Path) -> list[Path]:
    """Locate conversations.json / conversations-*.json under an import folder."""
    files: list[Path] = []
    for path in sorted(import_dir.rglob("*")):
        if not path.is_file():
            continue
        if is_chatgpt_conversation_file(path.name):
            files.append(path)
    return files


def parse_unix_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            # ChatGPT uses seconds; guard against ms.
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(value, str) and value.strip():
            # ISO-ish fallback
            cleaned = value.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError, TypeError):
        return None
    return None


def load_conversation_payloads(files: list[Path]) -> list[Any]:
    payloads: list[Any] = []
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read %s: %s", path.name, exc)
            continue

        if isinstance(data, list):
            payloads.extend(data)
        elif isinstance(data, dict):
            # Some splits wrap conversations under a key.
            for key in ("conversations", "items", "data"):
                maybe = data.get(key)
                if isinstance(maybe, list):
                    payloads.extend(maybe)
                    break
            else:
                payloads.append(data)
        else:
            logger.warning("Unexpected JSON root in %s (%s)", path.name, type(data).__name__)
    return payloads


def walk_active_path(mapping: dict[str, Any], current_node: str | None) -> list[str]:
    """Return node IDs from root → leaf along the active branch."""
    if not mapping:
        return []

    start = current_node
    if not start or start not in mapping:
        # Fallback: pick a leaf (node with no children that still has a message).
        leaves = [
            node_id
            for node_id, node in mapping.items()
            if isinstance(node, dict) and not (node.get("children") or [])
        ]
        start = leaves[-1] if leaves else next(iter(mapping.keys()), None)

    if not start:
        return []

    path_rev: list[str] = []
    seen: set[str] = set()
    node_id: str | None = start

    while node_id and node_id not in seen:
        seen.add(node_id)
        path_rev.append(node_id)
        node = mapping.get(node_id)
        if not isinstance(node, dict):
            break
        parent = node.get("parent")
        node_id = parent if isinstance(parent, str) and parent in mapping else None

    path_rev.reverse()
    return path_rev


def parse_conversation_node(raw: Any) -> ParsedConversation | None:
    if not isinstance(raw, dict):
        return None

    if raw.get("is_deleted") is True or raw.get("isDeleted") is True:
        return None

    external_id = (
        raw.get("conversation_id")
        or raw.get("id")
        or raw.get("conversationId")
    )
    if not external_id:
        return None
    external_id = str(external_id)

    title = raw.get("title")
    if title is not None:
        title = str(title).strip() or None

    created_at = parse_unix_timestamp(raw.get("create_time") or raw.get("createTime"))
    updated_at = parse_unix_timestamp(raw.get("update_time") or raw.get("updateTime"))

    mapping = raw.get("mapping")
    if mapping is None:
        mapping = {}
    if not isinstance(mapping, dict):
        return ParsedConversation(
            external_id=external_id,
            title=title,
            created_at=created_at,
            updated_at=updated_at,
            messages=[],
        )

    current_node = raw.get("current_node") or raw.get("currentNode")
    if current_node is not None:
        current_node = str(current_node)

    path = walk_active_path(mapping, current_node)
    messages: list[ParsedMessage] = []
    sequence = 0

    for node_id in path:
        node = mapping.get(node_id)
        if not isinstance(node, dict):
            continue

        message = node.get("message")
        # Synthetic root / empty nodes have null message — skip.
        if not isinstance(message, dict):
            continue

        try:
            msg_external = str(message.get("id") or node.get("id") or node_id)
            author = message.get("author") if isinstance(message.get("author"), dict) else {}
            role = normalize_role(author.get("role") if isinstance(author, dict) else None)
            content = extract_message_text(message)
            msg_created = parse_unix_timestamp(
                message.get("create_time") or message.get("createTime")
            )

            parent_raw = node.get("parent")
            parent_external = str(parent_raw) if isinstance(parent_raw, str) and parent_raw else None
            # Parent may be a synthetic root with no stored message — leave null later.

            messages.append(
                ParsedMessage(
                    external_id=msg_external,
                    parent_external_id=parent_external,
                    role=role,
                    content=content,
                    created_at=msg_created,
                    sequence_number=sequence,
                )
            )
            sequence += 1
        except Exception as exc:  # noqa: BLE001 — skip malformed nodes
            logger.warning(
                "Skipping malformed message node %s in conversation %s: %s",
                node_id,
                external_id,
                exc,
            )
            continue

    # Re-map parent_external_id to only point at messages we kept.
    kept_ids = {m.external_id for m in messages}
    for msg in messages:
        if msg.parent_external_id and msg.parent_external_id not in kept_ids:
            msg.parent_external_id = None

    return ParsedConversation(
        external_id=external_id,
        title=title,
        created_at=created_at,
        updated_at=updated_at,
        messages=messages,
    )


def parse_chatgpt_export(import_dir: Path) -> ParseResult:
    files = find_conversation_files(import_dir)
    if not files:
        raise FileNotFoundError(
            "No conversations.json (or conversations-*.json) found in import folder."
        )

    logger.info("Import started — parsing %d conversation file(s) from %s", len(files), import_dir.name)

    payloads = load_conversation_payloads(files)
    logger.info("Conversation count in export: %d", len(payloads))

    result = ParseResult()
    for raw in payloads:
        try:
            parsed = parse_conversation_node(raw)
            if parsed is None:
                result.skipped += 1
                continue
            result.conversations.append(parsed)
        except Exception as exc:  # noqa: BLE001 — never crash on one bad conversation
            result.skipped += 1
            warning = f"Skipped malformed conversation: {exc}"
            result.warnings.append(warning)
            logger.warning(warning)

    message_total = sum(c.message_count for c in result.conversations)
    logger.info(
        "Parsed conversations=%d messages=%d skipped=%d",
        len(result.conversations),
        message_total,
        result.skipped,
    )
    return result


def iter_conversation_batches(
    conversations: list[ParsedConversation],
    batch_size: int = 100,
) -> Iterator[list[ParsedConversation]]:
    for i in range(0, len(conversations), batch_size):
        yield conversations[i : i + batch_size]
