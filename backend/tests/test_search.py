from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import chatgpt_conversation, export_zip


def _import_and_parse(client: TestClient) -> None:
    payload = export_zip(
        [
            chatgpt_conversation(
                conversation_id="g1",
                title="Grafana alert architecture",
                messages=[
                    ("u1", "user", "How should we monitor Grafana alerts?"),
                    ("a1", "assistant", "Use Prometheus metrics and Grafana dashboards."),
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


def test_exact_keyword_search(client: TestClient) -> None:
    _import_and_parse(client)
    response = client.get("/api/search", params={"q": "Grafana", "mode": "keyword"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    titles = {item["conversation_title"] for item in body["results"]}
    assert "Grafana alert architecture" in titles


def test_partial_keyword_search(client: TestClient) -> None:
    _import_and_parse(client)
    response = client.get("/api/search", params={"q": "Graf", "mode": "keyword"})
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_search_no_results(client: TestClient) -> None:
    _import_and_parse(client)
    response = client.get("/api/search", params={"q": "xyzzyplugh", "mode": "keyword"})
    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["total"] == 0


def test_keyword_search_can_scope_to_one_conversation(client: TestClient) -> None:
    _import_and_parse(client)
    items = client.get("/api/conversations").json()["items"]
    redis = next(item for item in items if item["title"] == "Redis caching")
    grafana = next(item for item in items if item["title"] == "Grafana alert architecture")

    from app.db.session import get_session_factory
    from app.retrieval.hybrid import search_fts

    db = get_session_factory()()
    try:
        hits, _ = search_fts(
            db,
            "Grafana Redis FastAPI",
            limit=20,
            conversation_ids=[redis["id"]],
        )
    finally:
        db.close()

    assert hits
    assert all(hit.conversation_id == redis["id"] for hit in hits)
    assert grafana["id"] not in {hit.conversation_id for hit in hits}


def test_conversation_filters_and_pagination(client: TestClient) -> None:
    _import_and_parse(client)
    listed = client.get(
        "/api/conversations",
        params={"page": 1, "page_size": 1, "sort": "newest", "source": "ChatGPT"},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1

    search = client.get("/api/conversations", params={"search": "Redis"})
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["title"] == "Redis caching"


def test_conversation_messages_pagination(client: TestClient) -> None:
    _import_and_parse(client)
    listed = client.get("/api/conversations")
    convo_id = listed.json()["items"][0]["id"]
    messages = client.get(
        f"/api/conversations/{convo_id}/messages",
        params={"page": 1, "page_size": 1},
    )
    assert messages.status_code == 200
    body = messages.json()
    assert body["total"] >= 1
    assert len(body["items"]) == 1
    assert body["items"][0]["role"] in {"user", "assistant", "system", "tool"}
    assert "has_after" in body
    assert "has_before" in body
