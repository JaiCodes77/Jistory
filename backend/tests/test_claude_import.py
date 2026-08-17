from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import reset_engine
from tests.helpers import (
    chatgpt_conversation,
    claude_conversation,
    claude_export_zip,
    export_zip,
    zip_bytes,
)


def test_valid_claude_zip_upload(client: TestClient) -> None:
    payload = claude_export_zip([claude_conversation()])
    response = client.post(
        "/api/import/claude",
        files={"file": ("claude-export.zip", payload, "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["status"] == "uploaded"
    assert body["source"] == "Claude"
    assert body["importId"]


def test_claude_zip_missing_conversations(client: TestClient) -> None:
    payload = zip_bytes({"users.json": "[]"})
    response = client.post(
        "/api/import/claude",
        files={"file": ("claude-export.zip", payload, "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "missing_export_files"


def test_claude_invalid_zip(client: TestClient) -> None:
    response = client.post(
        "/api/import/claude",
        files={"file": ("claude-export.zip", b"this is not a zip", "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["code"] in {"invalid_type", "corrupted_zip"}


def test_claude_oversized_zip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 't.db'}")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("MAX_IMPORT_SIZE_MB", "0")
    monkeypatch.setenv("IMPORTS_DIR", str(tmp_path / "imports"))
    get_settings.cache_clear()
    reset_engine()
    from app.main import create_app

    with TestClient(create_app()) as client:
        payload = claude_export_zip([claude_conversation()])
        response = client.post(
            "/api/import/claude",
            files={"file": ("claude-export.zip", payload, "application/zip")},
        )
        assert response.status_code == 413
        assert response.json()["code"] == "file_too_large"
    reset_engine()
    get_settings.cache_clear()


def test_claude_parse_response_shape(client: TestClient) -> None:
    payload = claude_export_zip([claude_conversation()])
    uploaded = client.post(
        "/api/import/claude",
        files={"file": ("a.zip", payload, "application/zip")},
    )
    parsed = client.post(f"/api/import/{uploaded.json()['importId']}/parse")
    body = parsed.json()
    assert parsed.status_code == 200, parsed.text
    assert body["success"] is True
    assert body["conversations"] == 1
    assert body["messages"] == 2
    assert "elapsed_ms" in body
    assert body["status"] in {"indexing", "parsed", "ready", "completed"}


def test_claude_import_is_keyword_searchable(client: TestClient) -> None:
    payload = claude_export_zip([claude_conversation()])
    uploaded = client.post(
        "/api/import/claude",
        files={"file": ("a.zip", payload, "application/zip")},
    )
    parsed = client.post(f"/api/import/{uploaded.json()['importId']}/parse")
    assert parsed.status_code == 200
    response = client.get("/api/search", params={"q": "Postgres", "mode": "keyword"})
    assert response.status_code == 200
    titles = {item["conversation_title"] for item in response.json()["results"]}
    assert "Postgres vs MongoDB for metrics" in titles


def test_chatgpt_export_still_uses_chatgpt_endpoint(client: TestClient) -> None:
    payload = export_zip([chatgpt_conversation()])
    response = client.post(
        "/api/import/chatgpt",
        files={"file": ("export.zip", payload, "application/zip")},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "ChatGPT"
