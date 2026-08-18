from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ask.service import ask
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.llm.base import ChatTurn, LLMProvider
from app.models.conversation import Conversation
from tests.helpers import chatgpt_conversation, export_zip


class RecordingLLM(LLMProvider):
    model_name = "fake-llm"

    def generate(self, *, system: str, prompt: str, history: list[ChatTurn]) -> str:
        return "You chose Redis as the cache. [1]"


def _seed_two(client: TestClient) -> None:
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
    parsed = client.post(f"/api/import/{uploaded.json()['importId']}/parse")
    assert parsed.status_code == 200


def _conversation_id(client: TestClient, title: str) -> str:
    items = client.get("/api/conversations").json()["items"]
    return next(item["id"] for item in items if item["title"] == title)


def test_ask_session_resume_returns_turns_and_tags(client: TestClient) -> None:
    _seed_two(client)
    redis_id = _conversation_id(client, "Redis caching")
    question = "What did I decide about Redis caching for FastAPI in this project?"
    db = get_session_factory()()
    try:
        result = ask(
            db,
            get_settings(),
            message=question,
            conversation_id=None,
            tagged_conversation_ids=[redis_id],
            llm=RecordingLLM(),
        )
        session_id = result.conversation_id
    finally:
        db.close()

    listed = client.get("/api/ask/sessions")
    assert listed.status_code == 200
    items = listed.json()["items"]
    match = next(item for item in items if item["id"] == session_id)
    assert match["title"] == question
    assert match["tagged_conversation_ids"] == [redis_id]

    detail = client.get(f"/api/ask/sessions/{session_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["tagged_conversation_ids"] == [redis_id]
    assert [row["id"] for row in body["tagged_conversations"]] == [redis_id]
    assert len(body["turns"]) == 2
    assert body["turns"][0]["role"] == "user"
    assert body["turns"][0]["content"] == question
    assert body["turns"][1]["role"] == "assistant"
    assert body["turns"][1]["sources"]
    assert all(source["conversation_id"] == redis_id for source in body["turns"][1]["sources"])


def test_ask_session_title_is_truncated(client: TestClient) -> None:
    _seed_two(client)
    question = "What did I decide about Redis " + ("caching " * 40)
    db = get_session_factory()()
    try:
        result = ask(
            db,
            get_settings(),
            message=question,
            conversation_id=None,
            llm=RecordingLLM(),
        )
        session_id = result.conversation_id
    finally:
        db.close()

    detail = client.get(f"/api/ask/sessions/{session_id}").json()
    assert detail["title"]
    assert len(detail["title"]) <= 80
    assert detail["title"].endswith("…")


def test_delete_ask_session_does_not_delete_conversations(client: TestClient) -> None:
    _seed_two(client)
    db = get_session_factory()()
    try:
        result = ask(
            db,
            get_settings(),
            message="What did I decide about Redis?",
            conversation_id=None,
            llm=RecordingLLM(),
        )
        session_id = result.conversation_id
        before = int(db.scalar(select(func.count()).select_from(Conversation)) or 0)
    finally:
        db.close()

    assert before == 2
    deleted = client.delete(f"/api/ask/sessions/{session_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/ask/sessions/{session_id}").status_code == 404
    assert client.get("/api/conversations").json()["total"] == 2

    db = get_session_factory()()
    try:
        assert int(db.scalar(select(func.count()).select_from(Conversation)) or 0) == 2
    finally:
        db.close()
