"""Import a public ChatGPT or Claude share link into SQLite."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, Settings
from app.imports.chatgpt.share import (
    fetch_share_html,
    parse_share_html,
    parse_share_url,
    parsed_conversation_from_share,
)
from app.imports.claude.share import fetch_share_html as fetch_claude_html
from app.imports.claude.share import fetch_snapshot_json as fetch_claude_snapshot
from app.imports.claude.share import parse_share_html as parse_claude_html
from app.imports.claude.share import parse_share_url as parse_claude_url
from app.imports.claude.share import parsed_conversation_from_share as parsed_claude_conversation
from app.imports.extractor import allocate_import_directory, cleanup_directory
from app.imports.parse_service import ParseService
from app.imports.validators import ImportValidationError
from app.models.import_job import ImportJob, ImportSource, ImportStatus
from app.schemas.parse import ParseJobResponse

logger = logging.getLogger("jistory.share")


class ShareImportService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.imports_root = Path(settings.imports_dir)

    def import_share_url(self, url: str) -> ParseJobResponse:
        canonical, share_id = parse_share_url(url)
        html = fetch_share_html(canonical)
        payload = parse_share_html(html)
        parsed_conversation_from_share(payload)
        return self._persist_and_parse(
            canonical=canonical,
            share_id=share_id,
            payload=payload,
            source=ImportSource.CHATGPT,
            filename=f"share-{share_id}.json",
            notes=f"Imported from public share link {canonical}.",
        )

    def import_claude_share_url(self, url: str) -> ParseJobResponse:
        canonical, share_id = parse_claude_url(url)
        html = fetch_claude_html(canonical)
        try:
            payload = parse_claude_html(html)
        except ImportValidationError as exc:
            if exc.code != "share_parse_failed":
                raise
            payload = fetch_claude_snapshot(share_id)
        parsed_claude_conversation(payload)
        return self._persist_and_parse(
            canonical=canonical,
            share_id=share_id,
            payload=payload,
            source=ImportSource.CLAUDE,
            filename=f"claude-share-{share_id}.json",
            notes=f"Imported from public Claude share link {canonical}.",
        )

    def _persist_and_parse(
        self,
        *,
        canonical: str,
        share_id: str,
        payload: dict[str, Any],
        source: ImportSource,
        filename: str,
        notes: str,
    ) -> ParseJobResponse:
        import_dir = allocate_import_directory(self.imports_root)
        job: ImportJob | None = None
        try:
            snapshot = json.dumps([payload], ensure_ascii=False, indent=2)
            (import_dir / "conversations.json").write_text(snapshot, encoding="utf-8")
            (import_dir / "share-url.txt").write_text(canonical + "\n", encoding="utf-8")

            try:
                relative_folder = str(import_dir.relative_to(DATA_DIR))
            except ValueError:
                relative_folder = str(import_dir)

            job = ImportJob(
                source=source.value,
                imported_at=datetime.now(timezone.utc),
                folder_path=relative_folder,
                status=ImportStatus.UPLOADED.value,
                file_size=len(snapshot.encode("utf-8")),
                original_filename=filename,
                notes=notes,
            )
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)

            logger.info("Share import stored — job=%s share_id=%s source=%s", job.id, share_id, source.value)
            return ParseService(db=self.db, settings=self.settings).parse_import_job(job.id)
        except ImportValidationError:
            if job is None:
                cleanup_directory(import_dir)
            raise
        except Exception as exc:
            if job is None:
                cleanup_directory(import_dir)
            logger.exception("Share import failed")
            raise ImportValidationError(
                "Failed to import that share link. Please try again.",
                code="share_import_failed",
            ) from exc
