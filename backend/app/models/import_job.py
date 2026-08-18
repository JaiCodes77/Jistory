import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportSource(str, enum.Enum):
    CHATGPT = "ChatGPT"
    CLAUDE = "Claude"
    CURSOR = "Cursor"


class ImportStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PARSED = "parsed"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    # Legacy values kept so existing rows remain readable.
    PENDING = "pending"
    COMPLETED = "completed"


PARSEABLE_STATUSES = frozenset(
    {
        ImportStatus.UPLOADED.value,
        ImportStatus.PROCESSING.value,
        ImportStatus.PARSED.value,
        ImportStatus.INDEXING.value,
        ImportStatus.READY.value,
        ImportStatus.COMPLETED.value,
        ImportStatus.PENDING.value,
    }
)

READY_STATUSES = frozenset(
    {
        ImportStatus.READY.value,
        ImportStatus.COMPLETED.value,
    }
)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=ImportSource.CHATGPT.value,
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    folder_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ImportStatus.PENDING.value,
    )
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversations_imported: Mapped[int | None] = mapped_column(Integer, nullable=True)
    messages_imported: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversations_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunks_indexed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
