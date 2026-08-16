from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.config import SETTINGS_PATH, Settings, get_settings
from app.embeddings.runtime import get_embedding_status

logger = logging.getLogger("jistory.settings")

ALLOWED_EMBEDDING_PROVIDERS = {"local", "gemini"}


def _read_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read settings file")
        return {}
    return data if isinstance(data, dict) else {}


def settings_file_path(settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    url = cfg.database_url
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        return db_path.parent / "settings.json"
    return SETTINGS_PATH


def load_overrides(settings: Settings | None = None) -> dict:
    return _read_file(settings_file_path(settings))


def save_overrides(updates: dict, settings: Settings | None = None) -> dict:
    path = settings_file_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_overrides(settings)
    for key, value in updates.items():
        if value is None:
            continue
        if key == "gemini_api_key" and str(value).strip() == "":
            current.pop("gemini_api_key", None)
            continue
        current[key] = value
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def resolve_settings(settings: Settings) -> Settings:
    data = load_overrides(settings)
    updates: dict = {}
    if data.get("gemini_model"):
        updates["gemini_model"] = str(data["gemini_model"]).strip()
    file_key = str(data.get("gemini_api_key") or "").strip()
    if file_key and not settings.gemini_api_key:
        updates["gemini_api_key"] = file_key
    if data.get("retrieval_limit"):
        try:
            updates["retrieval_limit"] = max(1, min(32, int(data["retrieval_limit"])))
        except (TypeError, ValueError):
            pass
    provider = str(data.get("embedding_provider") or "").strip().lower()
    if provider in ALLOWED_EMBEDDING_PROVIDERS:
        updates["embedding_provider"] = provider
    if not updates:
        return settings
    return settings.model_copy(update=updates)


def public_settings(settings: Settings) -> dict:
    resolved = resolve_settings(settings)
    embedding = get_embedding_status()
    return {
        "llm_provider": "gemini",
        "gemini_model": resolved.gemini_model,
        "api_key_configured": bool(resolved.gemini_api_key),
        "embedding_provider": resolved.embedding_provider,
        "embedding_model": resolved.embedding_model,
        "retrieval_limit": resolved.retrieval_limit,
        "stored_locally": True,
        "sent_to_gemini_on_ask": True,
        "embedding_status": embedding["status"],
        "embedding_status_detail": embedding["detail"],
    }
