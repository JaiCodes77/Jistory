"""Text extraction helpers for ChatGPT message content."""

from __future__ import annotations

from typing import Any

ALLOWED_ROLES = frozenset({"user", "assistant", "system", "tool"})


def normalize_role(raw: Any) -> str:
    if not isinstance(raw, str):
        return "system"
    role = raw.strip().lower()
    if role in ALLOWED_ROLES:
        return role
    # ChatGPT occasionally emits roles like "tool" variants or "critic".
    if "assistant" in role:
        return "assistant"
    if "user" in role:
        return "user"
    if "tool" in role or "function" in role:
        return "tool"
    return "system"


def extract_text_from_parts(parts: Any) -> str:
    if parts is None:
        return ""

    if isinstance(parts, str):
        return parts.strip()

    if not isinstance(parts, list):
        return ""

    chunks: list[str] = []
    for part in parts:
        text = _extract_part_text(part)
        if text:
            chunks.append(text)

    return "\n".join(chunks).strip()


def _extract_part_text(part: Any) -> str:
    if part is None:
        return ""

    if isinstance(part, str):
        return part.strip()

    if not isinstance(part, dict):
        return ""

    # Explicit non-text payloads to ignore.
    content_type = str(part.get("content_type") or "").lower()
    if content_type in {
        "image_asset_pointer",
        "image",
        "audio",
        "video",
        "tether_browsing_display",
        "execution_output",
    }:
        return ""

    if "asset_pointer" in part or "image_asset_pointer" in part:
        return ""

    # Common text-bearing shapes.
    for key in ("text", "value", "caption"):
        value = part.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested_parts = part.get("parts")
    if nested_parts is not None:
        return extract_text_from_parts(nested_parts)

    return ""


def extract_message_text(message: dict[str, Any] | None) -> str:
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, dict):
        return ""

    content_type = str(content.get("content_type") or "").lower()
    if content_type in {"image_asset_pointer", "image"}:
        return ""

    return extract_text_from_parts(content.get("parts"))
