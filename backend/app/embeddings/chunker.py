from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.message import Message

ROLE_LABELS = {
    "user": "User",
    "assistant": "Assistant",
    "system": "System",
    "tool": "Tool",
}

MAX_CHARS = 2400
MAX_MESSAGES = 6
MAX_EMBED_CHARS = 4000


@dataclass
class ChunkDraft:
    conversation_id: str
    source: str
    timestamp: datetime | None
    text: str
    message_ids: list[str]


def chunk_messages(
    *,
    conversation_id: str,
    source: str,
    messages: list[Message],
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    bucket: list[Message] = []
    bucket_len = 0

    def flush() -> None:
        nonlocal bucket, bucket_len
        if not bucket:
            return
        lines = [_format_message(m) for m in bucket]
        text = "\n\n".join(lines)
        if len(text) > MAX_EMBED_CHARS:
            text = text[:MAX_EMBED_CHARS]
        times = [m.created_at for m in bucket if m.created_at is not None]
        drafts.append(
            ChunkDraft(
                conversation_id=conversation_id,
                source=source,
                timestamp=times[0] if times else bucket[0].created_at,
                text=text,
                message_ids=[m.id for m in bucket],
            )
        )
        bucket = []
        bucket_len = 0

    for message in sorted(messages, key=lambda m: m.sequence_number):
        if not (message.content or "").strip():
            continue
        piece = _format_message(message)
        if bucket and (bucket_len + len(piece) > MAX_CHARS or len(bucket) >= MAX_MESSAGES):
            flush()
        bucket.append(message)
        bucket_len += len(piece)

    flush()
    return drafts


def _format_message(message: Message) -> str:
    label = ROLE_LABELS.get(message.role, message.role.title())
    return f"{label}: {(message.content or '').strip()}"
