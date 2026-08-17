import zipfile
from pathlib import Path

from fastapi import UploadFile

# ChatGPT and Claude exports include conversation data under one of these patterns.
REQUIRED_CONVERSATION_NAMES = ("conversations.json",)
REQUIRED_CONVERSATION_PREFIX = "conversations-"
REQUIRED_CONVERSATION_SUFFIX = ".json"

# Companion files commonly present in ChatGPT exports (informational).
KNOWN_EXPORT_FILES = {
    "conversations.json",
    "chat.html",
    "user.json",
    "message_feedback.json",
    "model_comparisons.json",
    "shared_conversations.json",
}


class ImportValidationError(Exception):
    def __init__(self, message: str, code: str = "validation_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def validate_filename(filename: str | None, *, source_label: str = "export") -> str:
    if not filename:
        raise ImportValidationError("No file was provided.", code="missing_file")

    name = Path(filename).name
    if not name.lower().endswith(".zip"):
        raise ImportValidationError(
            f"File must be a {source_label} ZIP (.zip).",
            code="invalid_type",
        )
    return name


def validate_file_size(size: int, max_bytes: int) -> None:
    if size <= 0:
        raise ImportValidationError("Uploaded file is empty.", code="empty_file")

    if size > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        actual_mb = size / (1024 * 1024)
        raise ImportValidationError(
            f"File is too large ({actual_mb:.1f} MB). Maximum allowed size is {max_mb:.0f} MB.",
            code="file_too_large",
        )


def validate_content_type(content_type: str | None) -> None:
    if not content_type:
        return

    allowed = {
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
        "multipart/form-data",
    }
    # Some browsers send empty or generic types for ZIPs; don't hard-fail on that.
    if content_type.split(";")[0].strip().lower() not in allowed and "zip" not in content_type.lower():
        # Soft check — filename + zip magic are the real guards.
        return


def is_chatgpt_conversation_file(name: str) -> bool:
    return _is_conversations_json(name)


def is_claude_conversation_file(name: str) -> bool:
    return _is_conversations_json(name)


def _is_conversations_json(name: str) -> bool:
    basename = Path(name).name.lower()
    if basename in REQUIRED_CONVERSATION_NAMES:
        return True
    return basename.startswith(REQUIRED_CONVERSATION_PREFIX) and basename.endswith(
        REQUIRED_CONVERSATION_SUFFIX
    )


def zip_member_names(zip_path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Force CRC checks by reading the central directory and testing members.
            bad = zf.testzip()
            if bad is not None:
                raise ImportValidationError(
                    f"ZIP archive is corrupted (failed member: {bad}).",
                    code="corrupted_zip",
                )
            return zf.namelist()
    except zipfile.BadZipFile as exc:
        raise ImportValidationError(
            "File is not a valid ZIP archive or the archive is corrupted.",
            code="corrupted_zip",
        ) from exc
    except ImportValidationError:
        raise
    except Exception as exc:
        raise ImportValidationError(
            "Unable to read ZIP archive. The file may be corrupted.",
            code="corrupted_zip",
        ) from exc


def validate_chatgpt_export_contents(member_names: list[str]) -> list[str]:
    """Ensure the archive looks like a ChatGPT data export."""
    basenames = [Path(name).name for name in member_names if not name.endswith("/")]
    conversation_files = [name for name in basenames if is_chatgpt_conversation_file(name)]

    if not conversation_files:
        raise ImportValidationError(
            "This ZIP does not look like a ChatGPT export. "
            "Expected conversations.json (or conversations-*.json).",
            code="missing_export_files",
        )

    return sorted(set(conversation_files))


def validate_claude_export_contents(member_names: list[str]) -> list[str]:
    """Ensure the archive looks like a Claude data export."""
    basenames = [Path(name).name for name in member_names if not name.endswith("/")]
    conversation_files = [name for name in basenames if is_claude_conversation_file(name)]

    if not conversation_files:
        raise ImportValidationError(
            "This ZIP does not look like a Claude export. "
            "Expected conversations.json (or conversations-*.json).",
            code="missing_export_files",
        )

    return sorted(set(conversation_files))


async def read_upload_with_limit(upload: UploadFile, max_bytes: int) -> bytes:
    """Read upload into memory while enforcing the size limit."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ImportValidationError(
                f"File is too large. Maximum allowed size is {max_bytes / (1024 * 1024):.0f} MB.",
                code="file_too_large",
            )
        chunks.append(chunk)

    data = b"".join(chunks)
    validate_file_size(len(data), max_bytes)
    return data


def looks_like_zip(data: bytes) -> bool:
    # ZIP local file header or empty archive / EOCD magic
    return data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06")
