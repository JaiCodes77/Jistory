import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.imports.validators import ImportValidationError


def make_import_folder_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    return stamp


def allocate_import_directory(imports_root: Path, now: datetime | None = None) -> Path:
    """Create a unique import directory under imports_root."""
    imports_root.mkdir(parents=True, exist_ok=True)

    base = make_import_folder_name(now)
    candidate = imports_root / base
    if not candidate.exists():
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate

    # Avoid overwriting if two imports land in the same second.
    candidate = imports_root / f"{base}_{uuid4().hex[:8]}"
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _is_within_directory(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def extract_zip(zip_path: Path, destination: Path) -> list[str]:
    """
    Extract a ZIP into destination with zip-slip protection.
    Returns the list of extracted relative paths.
    """
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                # Skip directory entries; they are created as needed.
                member_name = info.filename
                if not member_name or member_name.endswith("/"):
                    continue

                # Normalize and reject absolute / traversal paths.
                target = (destination / member_name).resolve()
                if not _is_within_directory(destination, target):
                    raise ImportValidationError(
                        "ZIP archive contains an unsafe path and was rejected.",
                        code="unsafe_zip",
                    )

                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted.append(str(target.relative_to(destination)))
    except ImportValidationError:
        raise
    except zipfile.BadZipFile as exc:
        raise ImportValidationError(
            "ZIP archive is corrupted and could not be extracted.",
            code="corrupted_zip",
        ) from exc
    except Exception as exc:
        raise ImportValidationError(
            f"Failed to extract ZIP archive: {exc}",
            code="extract_failed",
        ) from exc

    if not extracted:
        raise ImportValidationError(
            "ZIP archive is empty.",
            code="empty_archive",
        )

    return extracted


def cleanup_directory(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
