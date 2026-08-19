from __future__ import annotations

import time

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, or_, select

from app.db.session import get_session_factory
from app.embeddings.jobs import wait_for_background_jobs
from app.graph.builder import ConversationNode, score_pair
from app.graph.topics import extract_terms
from app.models.graph import ConversationEdge, GraphMeta
from tests.helpers import chatgpt_conversation, export_zip


def _wait_ready(client: TestClient, import_id: str, timeout: float = 6.0) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        body = client.get(f"/api/import/{import_id}").json()
        if body["status"] in {"ready", "completed", "parsed", "failed"}:
            return body
        time.sleep(0.05)
    return body


def _import_graph_fixture(client: TestClient) -> None:
    payload = export_zip(
        [
            chatgpt_conversation(
                conversation_id="g1",
                title="Grafana alert architecture",
                messages=[
                    ("u1", "user", "Should we use Grafana for alerts?"),
                    (
                        "a1",
                        "assistant",
                        "Yes. Use Grafana with Prometheus for monitoring and alerts.",
                    ),
                ],
            ),
            chatgpt_conversation(
                conversation_id="g2",
                title="Grafana dashboard layout",
                messages=[
                    ("u2", "user", "How should Grafana dashboards be laid out?"),
                    (
                        "a2",
                        "assistant",
                        "Keep Grafana dashboards simple: Prometheus panels and a few alert rows.",
                    ),
                ],
            ),
            chatgpt_conversation(
                conversation_id="r1",
                title="Redis caching",
                messages=[
                    ("u3", "user", "Should we cache with Redis?"),
                    ("a3", "assistant", "Yes, Redis is a good cache for FastAPI."),
                ],
            ),
        ]
    )
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    import_id = uploaded.json()["importId"]
    parsed = client.post(f"/api/import/{import_id}/parse")
    assert parsed.status_code == 200
    wait_for_background_jobs()
    status = _wait_ready(client, import_id)
    assert status["status"] in {"ready", "completed", "parsed"}


def _id_by_title(client: TestClient, title: str) -> str:
    items = client.get("/api/conversations").json()["items"]
    return next(item["id"] for item in items if item["title"] == title)


def test_extract_terms_skips_stopwords() -> None:
    terms = extract_terms("Should we use Grafana for Redis caching?")
    assert "grafana" in terms
    assert "redis" in terms
    assert "should" not in terms
    assert "use" not in terms
    junk = extract_terms("actually already mime_type Add screenshot")
    assert "actually" not in junk
    assert "already" not in junk
    assert "mime_type" not in junk
    assert "add" not in junk
    assert "screenshot" not in junk


def test_score_pair_links_shared_title_topics() -> None:
    left = ConversationNode(
        id="a",
        title="Grafana alerts",
        source="ChatGPT",
        message_count=2,
        created_at=None,
        updated_at=None,
        last_message_at=None,
        title_terms=extract_terms("Grafana alerts"),
        body_terms=extract_terms("Grafana Prometheus"),
    )
    right = ConversationNode(
        id="b",
        title="Grafana dashboards",
        source="ChatGPT",
        message_count=2,
        created_at=None,
        updated_at=None,
        last_message_at=None,
        title_terms=extract_terms("Grafana dashboards"),
        body_terms=extract_terms("Grafana panels"),
    )
    unrelated = ConversationNode(
        id="c",
        title="Redis caching",
        source="ChatGPT",
        message_count=2,
        created_at=None,
        updated_at=None,
        last_message_at=None,
        title_terms=extract_terms("Redis caching"),
        body_terms=extract_terms("Redis FastAPI cache"),
    )
    linked = score_pair(left, right)
    assert linked is not None
    assert "Grafana" in linked.reason
    assert score_pair(left, unrelated) is None


def test_graph_builds_after_index_and_related_is_explainable(client: TestClient) -> None:
    _import_graph_fixture(client)
    grafana_a = _id_by_title(client, "Grafana alert architecture")
    grafana_b = _id_by_title(client, "Grafana dashboard layout")
    redis_id = _id_by_title(client, "Redis caching")

    graph = client.get("/api/graph")
    assert graph.status_code == 200
    body = graph.json()
    assert len(body["nodes"]) == 3
    sample = body["nodes"][0]
    assert "degree" in sample
    assert isinstance(sample.get("topics"), list)
    assert body["built_at"] is not None
    node_ids = {node["id"] for node in body["nodes"]}
    assert {grafana_a, grafana_b, redis_id} <= node_ids

    pair_ids = {(edge["source_id"], edge["target_id"]) for edge in body["edges"]}
    grafana_pair = tuple(sorted((grafana_a, grafana_b)))
    assert grafana_pair in pair_ids or any(
        grafana_a in pair and grafana_b in pair for pair in pair_ids
    )
    reasons = " ".join(edge["reason"] for edge in body["edges"])
    assert "Grafana" in reasons or "similar content" in reasons

    related = client.get(f"/api/conversations/{grafana_a}/related")
    assert related.status_code == 200
    related_ids = [item["id"] for item in related.json()["items"]]
    assert grafana_b in related_ids
    assert redis_id not in related_ids
    grafana_item = next(item for item in related.json()["items"] if item["id"] == grafana_b)
    assert grafana_item["reason"]
    assert grafana_item["weight"] > 0
    grafana_node = next(node for node in body["nodes"] if node["id"] == grafana_a)
    assert grafana_node["degree"] >= 1
    assert any(topic.lower() == "grafana" for topic in grafana_node["topics"])

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["graph_edges"] >= 1
    assert dashboard["graph_connected"] >= 2


def test_graph_filters_by_min_weight_and_source(client: TestClient) -> None:
    _import_graph_fixture(client)
    graph = client.get("/api/graph", params={"min_weight": 0.99, "include_isolated": False})
    assert graph.status_code == 200
    assert graph.json()["nodes"] == [] or all(
        edge["weight"] >= 0.99 for edge in graph.json()["edges"]
    )

    filtered = client.get("/api/graph", params={"source": "Claude"})
    assert filtered.status_code == 200
    assert filtered.json()["nodes"] == []
    assert filtered.json()["edges"] == []


def test_forget_conversation_removes_edges(client: TestClient) -> None:
    _import_graph_fixture(client)
    grafana_a = _id_by_title(client, "Grafana alert architecture")
    grafana_b = _id_by_title(client, "Grafana dashboard layout")

    deleted = client.delete(f"/api/conversations/{grafana_a}")
    assert deleted.status_code == 200

    related = client.get(f"/api/conversations/{grafana_b}/related")
    assert related.status_code == 200
    assert grafana_a not in {item["id"] for item in related.json()["items"]}

    graph = client.get("/api/graph").json()
    for edge in graph["edges"]:
        assert grafana_a not in {edge["source_id"], edge["target_id"]}
    assert grafana_a not in {node["id"] for node in graph["nodes"]}

    db = get_session_factory()()
    try:
        leftover = db.scalar(
            select(func.count())
            .select_from(ConversationEdge)
            .where(
                or_(
                    ConversationEdge.source_id == grafana_a,
                    ConversationEdge.target_id == grafana_a,
                )
            )
        )
        assert int(leftover or 0) == 0
    finally:
        db.close()


def test_related_missing_conversation_404(client: TestClient) -> None:
    response = client.get("/api/conversations/00000000-0000-0000-0000-000000000000/related")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_graph_rebuild_endpoint(client: TestClient) -> None:
    _import_graph_fixture(client)
    db = get_session_factory()()
    try:
        db.execute(delete(ConversationEdge))
        meta = db.get(GraphMeta, 1)
        if meta is not None:
            meta.built_at = None
            db.add(meta)
        db.commit()
    finally:
        db.close()

    rebuilt = client.post("/api/graph/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["nodes"] == 3
    assert rebuilt.json()["edges"] >= 1

    graph = client.get("/api/graph").json()
    assert len(graph["nodes"]) == 3
    assert len(graph["edges"]) >= 1


def test_graph_lazy_builds_on_get(client: TestClient) -> None:
    _import_graph_fixture(client)
    db = get_session_factory()()
    try:
        db.execute(delete(ConversationEdge))
        meta = db.get(GraphMeta, 1)
        if meta is not None:
            meta.built_at = None
            db.add(meta)
        db.commit()
    finally:
        db.close()

    graph = client.get("/api/graph")
    assert graph.status_code == 200
    body = graph.json()
    assert len(body["nodes"]) == 3
    assert len(body["edges"]) >= 1
    assert body["built_at"] is not None
