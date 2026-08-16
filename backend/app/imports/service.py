from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, Settings
from app.imports.extractor import (
    allocate_import_directory,
    cleanup_directory,
    extract_zip,
)
from app.imports.validators import (
    ImportValidationError,
    looks_like_zip,
    read_upload_with_limit,
    validate_chatgpt_export_contents,
    validate_content_type,
    validate_filename,
    zip_member_names,
)
from app.models.import_job import ImportJob, ImportSource, ImportStatus
from app.schemas.import_job import ImportJobResponse


class ImportService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.imports_root = Path(settings.imports_dir)

    async def import_chatgpt_zip(self, upload: UploadFile) -> ImportJobResponse:
        filename = validate_filename(upload.filename)
        validate_content_type(upload.content_type)

        data = await read_upload_with_limit(upload, self.settings.max_import_bytes)

        if not looks_like_zip(data):
            raise ImportValidationError(
                "File is not a valid ZIP archive.",
                code="invalid_type",
            )

        import_dir = allocate_import_directory(self.imports_root)
        zip_path = import_dir / filename
        job: ImportJob | None = None

        try:
            zip_path.write_bytes(data)

            member_names = zip_member_names(zip_path)
            conversation_files = validate_chatgpt_export_contents(member_names)

            extracted = extract_zip(zip_path, import_dir)

            try:
                relative_folder = str(import_dir.relative_to(DATA_DIR))
            except ValueError:
                relative_folder = str(import_dir)
            notes = (
                f"Extracted {len(extracted)} file(s). "
                f"Conversation files: {', '.join(conversation_files)}."
            )

            job = ImportJob(
                source=ImportSource.CHATGPT.value,
                imported_at=datetime.now(timezone.utc),
                folder_path=relative_folder,
                status=ImportStatus.UPLOADED.value,
                file_size=len(data),
                original_filename=filename,
                notes=notes,
            )
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)

            return ImportJobResponse(
                success=True,
                importId=job.id,
                source=job.source,
                folder=job.folder_path,
                status=job.status,
                filename=job.original_filename,
                fileSize=job.file_size,
                importedAt=job.imported_at,
                notes=job.notes,
            )
        except ImportValidationError as exc:
            cleanup_directory(import_dir)
            self._record_failed_job(
                filename=filename,
                file_size=len(data),
                folder_path="",
                notes=exc.message,
            )
            raise
        except Exception as exc:
            cleanup_directory(import_dir)
            self._record_failed_job(
                filename=filename,
                file_size=len(data),
                folder_path="",
                notes=str(exc),
            )
            raise ImportValidationError(
                "Import failed due to an unexpected server error.",
                code="import_failed",
            ) from exc

    def _record_failed_job(
        self,
        *,
        filename: str,
        file_size: int,
        folder_path: str,
        notes: str,
    ) -> None:
        try:
            failed = ImportJob(
                source=ImportSource.CHATGPT.value,
                imported_at=datetime.now(timezone.utc),
                folder_path=folder_path or "failed",
                status=ImportStatus.FAILED.value,
                file_size=file_size,
                original_filename=filename,
                notes=notes,
            )
            self.db.add(failed)
            self.db.commit()
        except Exception:
            self.db.rollback()
