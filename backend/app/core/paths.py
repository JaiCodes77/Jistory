from pathlib import Path

from app.core.errors import AppError


def resolve_under_root(root: Path, candidate: str | Path) -> Path:
    """Resolve candidate under root. Rejects path traversal and absolute escapes."""
    root_resolved = root.resolve()
    path = Path(candidate)
    resolved = path.resolve() if path.is_absolute() else (root_resolved / path).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise AppError(
            "The requested path is invalid.",
            code="unsafe_path",
            status_code=400,
        ) from exc
    return resolved
