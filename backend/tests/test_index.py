from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.session import ensure_runtime_schema, reset_engine
from app.embeddings.errors import EmbeddingUnavailableError
from app.embeddings.jobs import wait_for_background_jobs
from tests.helpers import chatgpt_conversation, export_zip


def _wait_status(client: TestClient, import_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/import/{import_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"ready", "completed", "parsed", "failed"}:
            return body
        time.sleep(0.05)
    return body


def test_parse_returns_before_embeddings_finish(client: TestClient) -> None:
    payload = export_zip([chatgpt_conversation()])
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    parsed = client.post(f"/api/import/{uploaded.json()['importId']}/parse")
    assert parsed.status_code == 200
    body = parsed.json()
    assert body["status"] == "indexing"
    listed = client.get("/api/conversations")
    assert listed.json()["total"] == 1


def test_index_reaches_ready(client: TestClient) -> None:
    payload = export_zip([chatgpt_conversation()])
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    import_id = uploaded.json()["importId"]
    parsed = client.post(f"/api/import/{import_id}/parse")
    assert parsed.status_code == 200
    status = _wait_status(client, import_id)
    assert status["status"] in {"ready", "completed"}
    assert status.get("index_error") in {None, ""}


def test_local_embeddings_fail_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 't.db'}")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("MAX_IMPORT_SIZE_MB", "5")
    monkeypatch.setenv("IMPORTS_DIR", str(tmp_path / "imports"))
    get_settings.cache_clear()
    reset_engine()

    def boom(self):
        raise EmbeddingUnavailableError("Local embeddings require FastEmbed.")

    monkeypatch.setattr("app.embeddings.local.LocalEmbeddingProvider._load", boom)

    from app.main import create_app

    with TestClient(create_app()) as client:
        payload = export_zip([chatgpt_conversation()])
        uploaded = client.post(
            "/api/import/chatgpt",
            files={"file": ("a.zip", payload, "application/zip")},
        )
        import_id = uploaded.json()["importId"]
        parsed = client.post(f"/api/import/{import_id}/parse")
        assert parsed.status_code == 200
        status = _wait_status(client, import_id)
        assert status["status"] == "parsed"
        assert "FastEmbed" in (status.get("index_error") or "")
        search = client.get("/api/search", params={"q": "Grafana", "mode": "keyword"})
        assert search.status_code == 200
        assert search.json()["total"] >= 1

    wait_for_background_jobs()
    reset_engine()
    get_settings.cache_clear()


def test_unique_constraint_added_on_existing_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    raw = sqlite3.connect(db_path)
    raw.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, source TEXT, external_id TEXT, title TEXT)")
    raw.execute("INSERT INTO conversations VALUES ('a', 'ChatGPT', 'same', 'first')")
    raw.execute("INSERT INTO conversations VALUES ('b', 'ChatGPT', 'same', 'second')")
    raw.commit()
    raw.close()

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, conversation_id TEXT, parent_message_id TEXT)")
        )
        conn.execute(text("CREATE TABLE IF NOT EXISTS memory_chunks (id TEXT PRIMARY KEY, conversation_id TEXT)"))
        ensure_runtime_schema(conn)
        count = conn.execute(text("SELECT COUNT(*) FROM conversations")).scalar()
        indexes = {row[1] for row in conn.execute(text("PRAGMA index_list(conversations)")).fetchall()}
    engine.dispose()

    assert count == 1
    assert "uq_conversation_source_external" in indexes


def test_messages_around_citation_not_on_first_page(client: TestClient) -> None:
    messages = [(f"m{i}", "user" if i % 2 == 0 else "assistant", f"line {i} Grafana" if i == 40 else f"line {i}") for i in range(60)]
    payload = export_zip(
        [
            chatgpt_conversation(
                conversation_id="long",
                title="Long thread",
                messages=messages,
            )
        ]
    )
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    parsed = client.post(f"/api/import/{uploaded.json()['importId']}/parse")
    assert parsed.status_code == 200
    convo_id = client.get("/api/conversations").json()["items"][0]["id"]
    first_page = client.get(
        f"/api/conversations/{convo_id}/messages",
        params={"page": 1, "page_size": 10},
    ).json()
    assert len(first_page["items"]) == 10
    target = client.get(
        f"/api/conversations/{convo_id}/messages",
        params={"page": 1, "page_size": 10, "after": first_page["items"][-1]["sequence_number"]},
    ).json()
    assert target["items"]
    target_id = None
    page = 1
    found = None
    while page <= 10:
        body = client.get(
            f"/api/conversations/{convo_id}/messages",
            params={"page": page, "page_size": 10},
        ).json()
        found = next((item for item in body["items"] if "Grafana" in item["content"]), None)
        if found:
            target_id = found["id"]
            break
        if not body["has_after"]:
            break
        page += 1
    assert target_id
    around = client.get(
        f"/api/conversations/{convo_id}/messages",
        params={"page_size": 10, "around": target_id},
    ).json()
    ids = {item["id"] for item in around["items"]}
    assert target_id in ids
    assert around["has_before"] is True
