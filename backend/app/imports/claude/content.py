"""Text extraction helpers for Claude export messages."""

from __future__ import annotations

from typing import Any

ALLOWED_ROLES = frozenset({"user", "assistant", "system", "tool"})
SKIP_BLOCK_TYPES = frozenset(
    {
        "thinking",
        "redacted_thinking",
        "tool_use",
        "tool_result",
        "image",
        "image_asset_pointer",
    }
)


def normalize_role(raw: Any) -> str:
    if not isinstance(raw, str):
        return "system"
    role = raw.strip().lower()
    if role in {"human", "user"}:
        return "user"
    if role in {"assistant", "claude"}:
        return "assistant"
    if role in ALLOWED_ROLES:
        return role
    if "assistant" in role:
        return "assistant"
    if "user" in role or "human" in role:
        return "user"
    if "tool" in role or "function" in role:
        return "tool"
    return "system"


def extract_message_text(message: dict[str, Any] | None) -> str:
    if not isinstance(message, dict):
        return ""

    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    chunks: list[str] = []
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        chunks.append(content.strip())
    elif isinstance(content, list):
        for block in content:
            extracted = _extract_block_text(block)
            if extracted:
                chunks.append(extracted)

    for key in ("attachments", "files", "files_v2"):
        items = message.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            extracted = _extract_attachment_text(item)
            if extracted:
                chunks.append(extracted)

    return "\n\n".join(chunks).strip()


def _extract_block_text(block: Any) -> str:
    if isinstance(block, str):
        return block.strip()
    if not isinstance(block, dict):
        return ""
    block_type = str(block.get("type") or "").lower()
    if block_type in SKIP_BLOCK_TYPES:
        return ""
    text = block.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return ""


def _extract_attachment_text(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    extracted = item.get("extracted_content")
    if isinstance(extracted, str) and extracted.strip():
        return extracted.strip()
    return ""
