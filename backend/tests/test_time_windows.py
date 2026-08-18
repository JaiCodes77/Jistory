from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.ask.service import ask
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.llm.base import ChatTurn, LLMProvider
from app.retrieval.hybrid import search_fts
from tests.helpers import chatgpt_conversation, export_zip


class RecordingLLM(LLMProvider):
    model_name = "fake-llm"

    def generate(self, *, system: str, prompt: str, history: list[ChatTurn]) -> str:
        return "Answer from the dated window. [1]"


def _seed_dated(client: TestClient) -> None:
    old = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc).timestamp()
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).timestamp()
    payload = export_zip(
        [
            chatgpt_conversation(
                conversation_id="old-redis",
                title="Redis caching",
                create_time=old,
                messages=[
                    ("u2", "user", "Should we cache with Redis?"),
                    ("a2", "assistant", "Yes, Redis is a good cache for FastAPI."),
                ],
            ),
            chatgpt_conversation(
                conversation_id="new-grafana",
                title="Grafana alert architecture",
                create_time=recent,
                messages=[
                    ("u1", "user", "What should we use for Grafana alerts?"),
                    (
                        "a1",
                        "assistant",
                        "We should use Prometheus as the datasource and Grafana for alert rules.",
                    ),
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


def test_search_excludes_hits_outside_date_window(client: TestClient) -> None:
    _seed_dated(client)
    start = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    end = datetime.now(timezone.utc).isoformat()

    recent = client.get(
        "/api/search",
        params={"q": "Redis Grafana", "mode": "keyword", "date_from": start, "date_to": end},
    )
    assert recent.status_code == 200
    titles = {item["conversation_title"] for item in recent.json()["results"]}
    assert "Grafana alert architecture" in titles
    assert "Redis caching" not in titles

    old_window = client.get(
        "/api/search",
        params={
            "q": "Redis",
            "mode": "keyword",
            "date_from": "2024-01-01T00:00:00+00:00",
            "date_to": "2024-02-01T00:00:00+00:00",
        },
    )
    old_titles = {item["conversation_title"] for item in old_window.json()["results"]}
    assert "Redis caching" in old_titles
    assert "Grafana alert architecture" not in old_titles


def test_tagged_and_dated_retrieval_stays_in_tagged_ids(client: TestClient) -> None:
    _seed_dated(client)
    redis_id = _conversation_id(client, "Redis caching")
    grafana_id = _conversation_id(client, "Grafana alert architecture")
    start = datetime.now(timezone.utc) - timedelta(days=30)
    end = datetime.now(timezone.utc)

    db = get_session_factory()()
    try:
        hits, _ = search_fts(
            db,
            "Redis Grafana Prometheus FastAPI",
            limit=20,
            conversation_ids=[redis_id],
            date_from=start,
            date_to=end,
        )
        result = ask(
            db,
            get_settings(),
            message="What did I decide about Redis and Grafana?",
            conversation_id=None,
            tagged_conversation_ids=[redis_id],
            date_from=start,
            date_to=end,
            llm=RecordingLLM(),
        )
    finally:
        db.close()

    assert all(hit.conversation_id == redis_id for hit in hits)
    assert grafana_id not in {hit.conversation_id for hit in hits}
    assert all(source.conversation_id == redis_id for source in result.sources)
    assert grafana_id not in {source.conversation_id for source in result.sources}
