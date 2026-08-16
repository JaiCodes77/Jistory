from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import reset_engine


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "jistory.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("MAX_IMPORT_SIZE_MB", "5")
    monkeypatch.setenv("IMPORTS_DIR", str(tmp_path / "imports"))
    get_settings.cache_clear()
    reset_engine()

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    from app.embeddings.jobs import wait_for_background_jobs

    wait_for_background_jobs()
    reset_engine()
    get_settings.cache_clear()
