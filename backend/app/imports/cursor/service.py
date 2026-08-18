"""Import Cursor local state.vscdb / transcript folders the user explicitly selects."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, Settings
from app.imports.extractor import allocate_import_directory, cleanup_directory
from app.imports.parse_service import ParseService
from app.imports.validators import ImportValidationError, read_upload_with_limit
from app.models.import_job import ImportJob, ImportSource, ImportStatus
from app.schemas.parse import ParseJobResponse
from app.user_settings.store import load_overrides

logger = logging.getLogger("jistory.cursor")

SQLITE_PREFIX = b"SQLite format 3"


class CursorImportService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.imports_root = Path(settings.imports_dir)

    def import_from_path(self, raw_path: str | None) -> ParseJobResponse:
        path = self._resolve_user_path(raw_path)
        import_dir = allocate_import_directory(self.imports_root)
        try:
            copied = self._copy_source(path, import_dir)
            return self._record_and_parse(
                import_dir,
                filename=path.name,
                file_size=sum(item.stat().st_size for item in copied if item.is_file()),
                notes=f"Imported Cursor data from a user-selected path ({path.name}).",
            )
        except ImportValidationError:
            cleanup_directory(import_dir)
            raise
        except Exception as exc:
            cleanup_directory(import_dir)
            logger.exception("Cursor path import failed")
            raise ImportValidationError(
                "Failed to import Cursor data from that path.",
                code="cursor_import_failed",
            ) from exc

    async def import_upload(self, upload: UploadFile) -> ParseJobResponse:
        filename = upload.filename or "state.vscdb"
        if filename.lower().endswith(".zip"):
            raise ImportValidationError(
                "Cursor import expects a state.vscdb file or transcript, not a ZIP export.",
                code="invalid_type",
            )
        data = await read_upload_with_limit(upload, self.settings.max_import_bytes)
        import_dir = allocate_import_directory(self.imports_root)
        try:
            dest_name = "state.vscdb" if _looks_like_sqlite(data) else Path(filename).name
            dest = import_dir / dest_name
            dest.write_bytes(data)
            return self._record_and_parse(
                import_dir,
                filename=filename,
                file_size=len(data),
                notes="Imported Cursor data from an uploaded file.",
            )
        except ImportValidationError:
            cleanup_directory(import_dir)
            raise
        except Exception as exc:
            cleanup_directory(import_dir)
            logger.exception("Cursor upload import failed")
            raise ImportValidationError(
                "Failed to import the uploaded Cursor file.",
                code="cursor_import_failed",
            ) from exc

    def _resolve_user_path(self, raw_path: str | None) -> Path:
        text = (raw_path or "").strip()
        if not text:
            overrides = load_overrides(self.settings)
            text = str(overrides.get("cursor_import_path") or self.settings.cursor_import_path or "").strip()
        if not text:
            raise ImportValidationError(
                "Choose a Cursor state.vscdb file or transcript folder. Jistory does not scan your home directory.",
                code="missing_path",
            )
        lowered = text.lower()
        if lowered.startswith("http://") or lowered.startswith("https://"):
            raise ImportValidationError(
                "Cursor import is local-file only. Public share URLs are not supported.",
                code="cursor_share_unsupported",
            )
        path = Path(text).expanduser()
        if not path.is_absolute():
            raise ImportValidationError(
                "Provide an absolute path to state.vscdb or a transcript folder.",
                code="relative_path",
            )
        try:
            resolved = path.resolve()
        except OSError as exc:
            raise ImportValidationError(
                "That Cursor path could not be read.",
                code="missing_path",
            ) from exc
        if not resolved.exists():
            raise ImportValidationError(
                "That Cursor path was not found.",
                code="missing_path",
            )
        return resolved

    def _copy_source(self, source: Path, import_dir: Path) -> list[Path]:
        copied: list[Path] = []
        if source.is_file():
            dest = import_dir / ("state.vscdb" if _is_sqlite_file(source) else source.name)
            _copy_file(source, dest)
            copied.append(dest)
            return copied

        candidates: list[Path] = []
        direct_db = source / "state.vscdb"
        if direct_db.is_file():
            candidates.append(direct_db)
        nested = source / "globalStorage" / "state.vscdb"
        if nested.is_file():
            candidates.append(nested)
        for child in source.iterdir():
            if child.is_file() and child.suffix.lower() in {".vscdb", ".json", ".jsonl", ".sqlite", ".db"}:
                candidates.append(child)
            elif child.is_dir() and (child / "state.vscdb").is_file():
                candidates.append(child / "state.vscdb")

        unique: list[Path] = []
        seen: set[Path] = set()
        for item in candidates:
            resolved = item.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(resolved)

        if not unique:
            raise ImportValidationError(
                "No state.vscdb or transcript files were found in that folder.",
                code="missing_export_files",
            )

        sqlite_index = 0
        for item in unique:
            if _is_sqlite_file(item):
                dest_name = "state.vscdb" if sqlite_index == 0 else f"{item.parent.name}-{item.name}"
                sqlite_index += 1
            else:
                dest_name = item.name
            dest = import_dir / dest_name
            _copy_file(item, dest)
            copied.append(dest)
        return copied

    def _record_and_parse(
        self,
        import_dir: Path,
        *,
        filename: str,
        file_size: int,
        notes: str,
    ) -> ParseJobResponse:
        try:
            relative_folder = str(import_dir.relative_to(DATA_DIR))
        except ValueError:
            relative_folder = str(import_dir)
        job = ImportJob(
            source=ImportSource.CURSOR.value,
            imported_at=datetime.now(timezone.utc),
            folder_path=relative_folder,
            status=ImportStatus.UPLOADED.value,
            file_size=file_size,
            original_filename=filename,
            notes=notes,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        logger.info("Cursor import stored — job=%s", job.id)
        return ParseService(db=self.db, settings=self.settings).parse_import_job(job.id)


def _looks_like_sqlite(data: bytes) -> bool:
    return data.startswith(SQLITE_PREFIX)


def _is_sqlite_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(16).startswith(SQLITE_PREFIX)
    except OSError:
        return False


def _copy_file(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if _is_sqlite_file(source):
        src_conn = None
        dest_conn = None
        try:
            src_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
            dest_conn = sqlite3.connect(dest)
            src_conn.backup(dest_conn)
            return
        except sqlite3.Error:
            logger.info("SQLite backup copy unavailable; using filesystem copy")
        finally:
            if dest_conn is not None:
                dest_conn.close()
            if src_conn is not None:
                src_conn.close()
    shutil.copy2(source, dest)
    if _is_sqlite_file(source):
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(source) + suffix)
            if sidecar.is_file():
                shutil.copy2(sidecar, Path(str(dest) + suffix))
