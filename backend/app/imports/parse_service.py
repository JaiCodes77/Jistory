"""Orchestrate parsing an ImportJob into normalized SQLite rows."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, Settings
from app.imports.chatgpt.persistence import persist_conversations
from app.imports.extractor import resolve_import_directory
from app.imports.parsers import UnknownSourceError, get_parser
from app.imports.validators import ImportValidationError
from app.models.import_job import PARSEABLE_STATUSES, ImportJob, ImportStatus
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

        if job.status not in PARSEABLE_STATUSES:
            raise ImportValidationError(
                "This import cannot be parsed in its current state.",
                code="invalid_status",
            )

        if job.folder_path in {"", "failed"}:
            raise ImportValidationError(
                "Import folder is missing for this job.",
                code="missing_folder",
            )

        import_dir = self._resolve_import_dir(job.folder_path)
        if import_dir is None or not import_dir.exists() or not import_dir.is_dir():
            raise ImportValidationError(
                "Import folder not found. The export may have been removed.",
                code="missing_folder",
            )

        logger.info("Parse started — job=%s source=%s", job.id, job.source)
        source_label = job.source or "export"

        job.status = ImportStatus.PROCESSING.value
        self.db.commit()

        try:
            parser = get_parser(job.source)
            parse_result = parser.parse(import_dir)
        except UnknownSourceError as exc:
            self._mark_failed(job, "No parser is available for this import source.")
            raise ImportValidationError(str(exc), code="unknown_source") from exc
        except FileNotFoundError as exc:
            self._mark_failed(job, "The export does not contain a conversations file.")
            raise ImportValidationError(str(exc), code="missing_export_files") from exc
        except ImportValidationError as exc:
            self._mark_failed(job, exc.message)
            raise
        except Exception as exc:
            logger.exception("Parse failed for import %s", job.id)
            self._mark_failed(job, f"Failed to parse the {source_label} export.")
            raise ImportValidationError(
                f"Failed to parse the {source_label} export. Check that the ZIP is a valid export.",
                code="parse_failed",
            ) from exc

        try:
            conversations_count, messages_count = persist_conversations(
                self.db,
                import_job_id=job.id,
                source=job.source or "ChatGPT",
                conversations=parse_result.conversations,
            )
        except Exception as exc:
            logger.exception("Persist failed for import %s", job.id)
            self.db.rollback()
            self._mark_failed(job, "Failed to store parsed conversations.")
            raise ImportValidationError(
                "Failed to store parsed conversations. Please try again.",
                code="persist_failed",
            ) from exc

        elapsed_s = time.perf_counter() - started
        elapsed_ms = int(elapsed_s * 1000)
        elapsed_label = f"{elapsed_s:.1f}s"

        notes_parts = [
            job.notes or "",
            f"Parsed {conversations_count} conversations / {messages_count} messages "
            f"(skipped {parse_result.skipped}) in {elapsed_label}.",
        ]
        job.status = ImportStatus.PARSED.value
        job.conversations_imported = conversations_count
        job.messages_imported = messages_count
        job.conversations_skipped = parse_result.skipped
        job.index_error = None
        job.notes = " ".join(part for part in notes_parts if part).strip()

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        for warning in parse_result.warnings[:20]:
            logger.warning(warning)

        logger.info(
            "Parse complete — conversations=%d messages=%d skipped=%d elapsed_ms=%d",
            conversations_count,
            messages_count,
            parse_result.skipped,
            elapsed_ms,
        )

        job.status = ImportStatus.INDEXING.value
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        from app.embeddings.jobs import schedule_embedding_index

        schedule_embedding_index(job.id)

        return ParseJobResponse(
            success=True,
            importId=job.id,
            conversations=conversations_count,
            messages=messages_count,
            skipped=parse_result.skipped,
            elapsed=elapsed_label,
            elapsed_ms=elapsed_ms,
            status=job.status,
            chunks_indexed=job.chunks_indexed,
            index_error=job.index_error,
        )

    def _mark_failed(self, job: ImportJob, notes: str) -> None:
        try:
            job.status = ImportStatus.FAILED.value
            suffix = notes
            job.notes = f"{job.notes} {suffix}".strip() if job.notes else suffix
            self.db.add(job)
            self.db.commit()
        except Exception:
            self.db.rollback()

    def _resolve_import_dir(self, folder_path: str) -> Path | None:
        return resolve_import_directory(
            folder_path,
            imports_root=Path(self.settings.imports_dir),
            data_root=DATA_DIR,
        )
