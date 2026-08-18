from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.ask.service import ask
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.embeddings.jobs import wait_for_background_jobs
from app.llm.base import ChatTurn, LLMProvider
from app.models.chunk import MemoryChunk
from app.models.conversation import Conversation
from app.models.import_job import ImportJob, ImportStatus
from app.models.message import Message
from tests.helpers import chatgpt_conversation, export_zip


class RecordingLLM(LLMProvider):
    model_name = "fake-llm"

    def generate(self, *, system: str, prompt: str, history: list[ChatTurn]) -> str:
        return "Answer from remaining history. [1]"


def _import_two(client: TestClient) -> str:
    payload = export_zip(
        [
            chatgpt_conversation(
                conversation_id="g1",
                title="Grafana alert architecture",
                messages=[
                    ("u1", "user", "What should we use for Grafana alerts?"),
                    (
                        "a1",
                        "assistant",
                        "We should use Prometheus as the datasource and Grafana for alert rules.",
                    ),
                ],
            ),
            chatgpt_conversation(
                conversation_id="r1",
                title="Redis caching",
                messages=[
                    ("u2", "user", "Should we cache with Redis?"),
                    ("a2", "assistant", "Yes, Redis is a good cache for FastAPI."),
                ],
            ),
        ]
    )
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    import_id = uploaded.json()["importId"]
    parsed = client.post(f"/api/import/{import_id}/parse")
    assert parsed.status_code == 200
    wait_for_background_jobs()
    deadline = time.time() + 4
    while time.time() < deadline:
        status = client.get(f"/api/import/{import_id}").json()
        if status["status"] in {"ready", "completed", "parsed"}:
            break
        time.sleep(0.05)
    return import_id


def _conversation_id(client: TestClient, title: str) -> str:
    items = client.get("/api/conversations").json()["items"]
    return next(item["id"] for item in items if item["title"] == title)


def test_delete_conversation_removes_rows_fts_chunks_and_ask(client: TestClient) -> None:
    _import_two(client)
    grafana_id = _conversation_id(client, "Grafana alert architecture")
    redis_id = _conversation_id(client, "Redis caching")

    db = get_session_factory()()
    try:
        assert db.scalar(select(func.count()).select_from(Conversation)) == 2
        chunks_before = int(
            db.scalar(
                select(func.count()).select_from(MemoryChunk).where(
                    MemoryChunk.conversation_id == grafana_id
                )
            )
            or 0
        )
        assert chunks_before >= 1
        fts_before = db.execute(
            text("SELECT COUNT(*) FROM messages_fts WHERE conversation_id = :id"),
            {"id": grafana_id},
        ).scalar()
        assert int(fts_before or 0) >= 1
    finally:
        db.close()

    deleted = client.delete(f"/api/conversations/{grafana_id}")
    assert deleted.status_code == 200
    body = deleted.json()
    assert body["success"] is True
    assert body["conversations_deleted"] == 1
    assert client.get(f"/api/conversations/{grafana_id}").status_code == 404
    assert client.get("/api/conversations").json()["total"] == 1

    db = get_session_factory()()
    try:
        assert db.get(Conversation, grafana_id) is None
        assert db.get(Conversation, redis_id) is not None
        assert (
            db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == grafana_id))
            == 0
        )
        assert (
            db.scalar(
                select(func.count()).select_from(MemoryChunk).where(
                    MemoryChunk.conversation_id == grafana_id
                )
            )
            == 0
        )
        fts_after = db.execute(
            text("SELECT COUNT(*) FROM messages_fts WHERE conversation_id = :id"),
            {"id": grafana_id},
        ).scalar()
        assert int(fts_after or 0) == 0

        result = ask(
            db,
            get_settings(),
            message="What conclusion did I reach about Grafana alerts and Prometheus?",
            conversation_id=None,
            llm=RecordingLLM(),
        )
    finally:
        db.close()

    search = client.get("/api/search", params={"q": "Prometheus", "mode": "keyword"})
    titles = {item["conversation_title"] for item in search.json()["results"]}
    assert "Grafana alert architecture" not in titles

    redis_search = client.get("/api/search", params={"q": "Redis", "mode": "keyword"})
    assert redis_search.json()["total"] >= 1
    assert all(source.conversation_id != grafana_id for source in result.sources)


def test_delete_missing_conversation_returns_404(client: TestClient) -> None:
    response = client.delete("/api/conversations/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_delete_import_removes_conversations_and_job(client: TestClient) -> None:
    import_id = _import_two(client)
    status = client.get(f"/api/import/{import_id}").json()
    folder = status["folder"]
    assert client.get("/api/conversations").json()["total"] == 2

    deleted = client.delete(f"/api/import/{import_id}")
    assert deleted.status_code == 200
    assert deleted.json()["conversations_deleted"] == 2
    assert client.get(f"/api/import/{import_id}").status_code == 404
    assert client.get("/api/conversations").json()["total"] == 0

    db = get_session_factory()()
    try:
        assert db.scalar(select(func.count()).select_from(Conversation)) == 0
        assert db.scalar(select(func.count()).select_from(Message)) == 0
        assert db.scalar(select(func.count()).select_from(MemoryChunk)) == 0
        fts_count = db.execute(text("SELECT COUNT(*) FROM messages_fts")).scalar()
        assert int(fts_count or 0) == 0
        assert db.get(ImportJob, import_id) is None
    finally:
        db.close()

    if folder and folder not in {"", "failed"}:
        imports_root = Path(get_settings().imports_dir)
        leftover = imports_root / Path(folder).name
        assert not leftover.exists()


def test_reindex_import_with_index_error(client: TestClient) -> None:
    import_id = _import_two(client)
    db = get_session_factory()()
    try:
        job = db.get(ImportJob, import_id)
        assert job is not None
        job.status = ImportStatus.PARSED.value
        job.index_error = "Keyword search is ready, but semantic indexing failed. Try parsing again."
        db.add(job)
        db.commit()
    finally:
        db.close()

    reindexed = client.post(f"/api/import/{import_id}/reindex")
    assert reindexed.status_code == 200
    assert reindexed.json()["index_error"] in {None, ""}
    wait_for_background_jobs()
    deadline = time.time() + 4
    body: dict = {}
    while time.time() < deadline:
        body = client.get(f"/api/import/{import_id}").json()
        if body["status"] in {"ready", "completed", "parsed"}:
            break
        time.sleep(0.05)
    assert body["status"] in {"ready", "completed"}
    assert body.get("index_error") in {None, ""}
    assert (body.get("chunks_indexed") or 0) >= 1
