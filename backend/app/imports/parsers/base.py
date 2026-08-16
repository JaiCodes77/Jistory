"""Parser interfaces for conversation export formats.

Future parsers (Claude, Gemini, Cursor) should implement ConversationParser
without changing persistence or API layers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ParsedMessage:
    external_id: str
    parent_external_id: str | None
    role: str
    content: str
    created_at: datetime | None
    sequence_number: int


@dataclass
class ParsedConversation:
    external_id: str
    title: str | None
    created_at: datetime | None
    updated_at: datetime | None
    messages: list[ParsedMessage] = field(default_factory=list)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def first_message_at(self) -> datetime | None:
        times = [m.created_at for m in self.messages if m.created_at is not None]
        return min(times) if times else None

    @property
    def last_message_at(self) -> datetime | None:
        times = [m.created_at for m in self.messages if m.created_at is not None]
        return max(times) if times else None


@dataclass
class ParseResult:
    conversations: list[ParsedConversation] = field(default_factory=list)
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


class ConversationParser(ABC):
    """Source-specific export parser."""

    source: str

    @abstractmethod
    def parse(self, import_dir: Path) -> ParseResult:
        """Parse files in an extracted import directory into normalized records."""


class UnknownSourceError(ValueError):
    pass
