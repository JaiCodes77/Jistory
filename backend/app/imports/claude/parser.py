"""Parse Claude conversations.json into normalized dataclasses."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.imports.claude.content import extract_message_text, normalize_role
from app.imports.parsers.base import ParsedConversation, ParsedMessage, ParseResult
from app.imports.validators import ImportValidationError, is_claude_conversation_file

logger = logging.getLogger("jistory.parser.claude")


def find_conversation_files(import_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(import_dir.rglob("*")):
        if not path.is_file():
            continue
        if is_claude_conversation_file(path.name):
            files.append(path)
    return files


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(value, str) and value.strip():
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
            if isinstance(data.get("chat_messages"), list) and (
                data.get("uuid") or data.get("id") or data.get("conversation_uuid")
            ):
                payloads.append(data)
                continue
            for key in ("conversations", "items", "data", "chats"):
                maybe = data.get(key)
                if isinstance(maybe, list):
                    payloads.extend(maybe)
                    break
            else:
                payloads.append(data)
        else:
            logger.warning("Unexpected JSON root in %s (%s)", path.name, type(data).__name__)
    return payloads


def looks_like_chatgpt_conversation(raw: dict[str, Any]) -> bool:
    return isinstance(raw.get("mapping"), dict) and not isinstance(raw.get("chat_messages"), list)


def parse_conversation(raw: Any) -> ParsedConversation | None:
    if not isinstance(raw, dict):
        return None
    if looks_like_chatgpt_conversation(raw):
        return None
    if raw.get("is_deleted") is True or raw.get("isDeleted") is True:
        return None

    external_id = (
        raw.get("uuid")
        or raw.get("conversation_uuid")
        or raw.get("id")
        or raw.get("conversation_id")
    )
    if not external_id:
        return None
    external_id = str(external_id)

    title = raw.get("name") or raw.get("title") or raw.get("snapshot_name")
    if title is not None:
        title = str(title).strip() or None

    created_at = parse_timestamp(raw.get("created_at") or raw.get("createdAt") or raw.get("create_time"))
    updated_at = parse_timestamp(raw.get("updated_at") or raw.get("updatedAt") or raw.get("update_time"))

    messages_raw = raw.get("chat_messages")
    if messages_raw is None:
        messages_raw = raw.get("messages") or []
    if not isinstance(messages_raw, list):
        return ParsedConversation(
            external_id=external_id,
            title=title,
            created_at=created_at,
            updated_at=updated_at,
            messages=[],
        )

    indexed = [
        (index, message)
        for index, message in enumerate(messages_raw)
        if isinstance(message, dict)
    ]
    indexed.sort(key=lambda item: (_message_sort_key(item[1]), item[0]))

    messages: list[ParsedMessage] = []
    sequence = 0
    for _order, message in indexed:
        try:
            msg_external = str(
                message.get("uuid") or message.get("id") or f"{external_id}:{sequence}"
            )
            role = normalize_role(message.get("sender") or message.get("role"))
            content = extract_message_text(message)
            msg_created = parse_timestamp(
                message.get("created_at") or message.get("createdAt") or message.get("create_time")
            )
            parent_raw = message.get("parent_message_uuid") or message.get("parent")
            parent_external = str(parent_raw) if isinstance(parent_raw, str) and parent_raw else None
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
                "Skipping malformed message in conversation %s: %s",
                external_id,
                exc,
            )
            continue

    kept_ids = {msg.external_id for msg in messages}
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


def parse_claude_export(import_dir: Path) -> ParseResult:
    files = find_conversation_files(import_dir)
    if not files:
        raise FileNotFoundError(
            "No conversations.json (or conversations-*.json) found in import folder."
        )

    logger.info(
        "Import started — parsing %d Claude conversation file(s) from %s",
        len(files),
        import_dir.name,
    )

    payloads = load_conversation_payloads(files)
    dict_payloads = [item for item in payloads if isinstance(item, dict)]
    if dict_payloads and all(looks_like_chatgpt_conversation(item) for item in dict_payloads):
        raise ImportValidationError(
            "This ZIP looks like a ChatGPT export. Use the ChatGPT importer instead.",
            code="wrong_export_format",
        )

    logger.info("Conversation count in export: %d", len(payloads))

    result = ParseResult()
    for raw in payloads:
        try:
            parsed = parse_conversation(raw)
            if parsed is None:
                result.skipped += 1
                continue
            result.conversations.append(parsed)
        except Exception as exc:  # noqa: BLE001 — never crash on one bad conversation
            result.skipped += 1
            warning = f"Skipped malformed conversation: {exc}"
            result.warnings.append(warning)
            logger.warning(warning)

    message_total = sum(convo.message_count for convo in result.conversations)
    logger.info(
        "Parsed conversations=%d messages=%d skipped=%d",
        len(result.conversations),
        message_total,
        result.skipped,
    )
    return result


def _message_sort_key(message: dict[str, Any]) -> tuple[int, str]:
    index = message.get("index")
    if isinstance(index, int):
        return (index, "")
    if isinstance(index, str) and index.isdigit():
        return (int(index), "")
    created = message.get("created_at") or message.get("createdAt") or ""
    return (0, str(created))
