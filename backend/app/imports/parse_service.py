"""Orchestrate parsing an ImportJob into normalized SQLite rows."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, Settings
from app.imports.chatgpt.parser import parse_chatgpt_export
from app.imports.chatgpt.persistence import (
    delete_import_conversations,
    persist_conversations,
)
from app.imports.validators import ImportValidationError
from app.models.import_job import ImportJob, ImportStatus
from app.schemas.parse import ParseJobResponse

logger = logging.getLogger("jistory.parse")


class ParseService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def parse_import_job(self, import_id: str) -> ParseJobResponse:
        started = time.perf_counter()

        job = self.db.get(ImportJob, import_id)
        if job is None:
            raise ImportValidationError(
                f"Import job '{import_id}' was not found.",
                code="import_not_found",
            )

        if job.status == ImportStatus.FAILED.value:
            raise ImportValidationError(
                "This import failed and cannot be parsed.",
                code="import_failed",
            )

        if job.folder_path in {"", "failed"}:
            raise ImportValidationError(
                "Import folder is missing for this job.",
                code="missing_folder",
            )

        import_dir = self._resolve_import_dir(job.folder_path)
        if not import_dir.exists() or not import_dir.is_dir():
            raise ImportValidationError(
                f"Import folder not found: {job.folder_path}",
                code="missing_folder",
            )

        logger.info("Import started — job=%s folder=%s", job.id, job.folder_path)

        try:
            parse_result = parse_chatgpt_export(import_dir)
        except FileNotFoundError as exc:
            raise ImportValidationError(str(exc), code="missing_export_files") from exc
        except Exception as exc:
            logger.exception("Parse failed for import %s", job.id)
            raise ImportValidationError(
                f"Failed to parse ChatGPT export: {exc}",
                code="parse_failed",
            ) from exc

        # Idempotent: clear any prior rows for this import, then rewrite.
        delete_import_conversations(self.db, job.id)

        conversations_count, messages_count = persist_conversations(
            self.db,
            import_job_id=job.id,
            source=job.source or "ChatGPT",
            conversations=parse_result.conversations,
        )

        elapsed = time.perf_counter() - started
        elapsed_label = f"{elapsed:.1f}s"

        notes_parts = [
            job.notes or "",
            f"Parsed {conversations_count} conversations / {messages_count} messages "
            f"(skipped {parse_result.skipped}) in {elapsed_label}.",
        ]
        job.status = ImportStatus.PARSED.value
        job.conversations_imported = conversations_count
        job.messages_imported = messages_count
        job.conversations_skipped = parse_result.skipped
        job.notes = " ".join(part for part in notes_parts if part).strip()

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        for warning in parse_result.warnings[:20]:
            logger.warning(warning)

        logger.info(
            "Parse complete — conversations=%d messages=%d skipped=%d elapsed=%s",
            conversations_count,
            messages_count,
            parse_result.skipped,
            elapsed_label,
        )

        return ParseJobResponse(
            success=True,
            importId=job.id,
            conversations=conversations_count,
            messages=messages_count,
            skipped=parse_result.skipped,
            elapsed=elapsed_label,
            status=job.status,
        )

    def _resolve_import_dir(self, folder_path: str) -> Path:
        path = Path(folder_path)
        if path.is_absolute():
            return path
        return (DATA_DIR / path).resolve()
