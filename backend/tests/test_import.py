from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import reset_engine
from tests.helpers import chatgpt_conversation, export_zip, zip_bytes


def test_valid_zip_upload(client: TestClient) -> None:
    payload = export_zip([chatgpt_conversation()])
    response = client.post(
        "/api/import/chatgpt",
        files={"file": ("export.zip", payload, "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["status"] == "uploaded"
    assert body["importId"]


def test_invalid_zip(client: TestClient) -> None:
    response = client.post(
        "/api/import/chatgpt",
        files={"file": ("export.zip", b"this is not a zip", "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["code"] in {"invalid_type", "corrupted_zip"}


def test_corrupted_zip(client: TestClient) -> None:
    response = client.post(
        "/api/import/chatgpt",
        files={"file": ("export.zip", b"PK\x03\x04not-a-valid-archive", "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "corrupted_zip"


def test_missing_conversations_file(client: TestClient) -> None:
    payload = zip_bytes({"readme.txt": "hello"})
    response = client.post(
        "/api/import/chatgpt",
        files={"file": ("export.zip", payload, "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "missing_export_files"


def test_oversized_zip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 't.db'}")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("MAX_IMPORT_SIZE_MB", "0")
    monkeypatch.setenv("IMPORTS_DIR", str(tmp_path / "imports"))
    get_settings.cache_clear()
    reset_engine()
    from app.main import create_app

    with TestClient(create_app()) as client:
        payload = export_zip([chatgpt_conversation()])
        response = client.post(
            "/api/import/chatgpt",
            files={"file": ("export.zip", payload, "application/zip")},
        )
        assert response.status_code == 413
        assert response.json()["code"] == "file_too_large"
    reset_engine()
    get_settings.cache_clear()


def test_path_traversal_zip(client: TestClient) -> None:
    payload = zip_bytes(
        {
            "../../evil.txt": "nope",
            "conversations.json": "[]",
        }
    )
    response = client.post(
        "/api/import/chatgpt",
        files={"file": ("export.zip", payload, "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "unsafe_zip"
