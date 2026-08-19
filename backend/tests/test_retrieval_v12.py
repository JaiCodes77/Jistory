from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db.session import get_session_factory
from app.models.chunk import MemoryChunk
from app.retrieval.hybrid import (
    RetrievedChunk,
    fallback_conversation_chunks,
    reciprocal_rank_fusion,
)
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


def test_hybrid_total_does_not_grow_with_page(client: TestClient) -> None:
    _import_and_parse(client)
    page1 = client.get("/api/search", params={"q": "Grafana Redis", "mode": "hybrid", "page": 1, "page_size": 1})
    page2 = client.get("/api/search", params={"q": "Grafana Redis", "mode": "hybrid", "page": 2, "page_size": 1})
    assert page1.status_code == 200
    assert page2.status_code == 200
    assert page1.json()["total"] == page2.json()["total"]
    assert page1.json()["total"] >= 1


def test_source_dropdown_hides_unbuilt_importers(client: TestClient) -> None:
    sources = client.get("/api/conversations/sources").json()
    assert "Gemini" not in sources["items"]
    assert "ChatGPT" in sources["items"]
    assert "Claude" in sources["items"]
    assert "Cursor" in sources["items"]


def test_app_version_default_is_2_0() -> None:
    from app.core.config import Settings

    assert Settings.model_fields["app_version"].default == "2.0.0"


def test_overlapping_chunks_are_deduped() -> None:
    now = datetime.now(timezone.utc)
    left = RetrievedChunk(
        conversation_id="c1",
        message_id="m1",
        message_ids=["m1", "m2"],
        conversation_title="One",
        source="ChatGPT",
        timestamp=now,
        snippet="left",
        text="left",
        score=1.0,
        match_type="keyword",
    )
    right = RetrievedChunk(
        conversation_id="c1",
        message_id="m2",
        message_ids=["m2", "m3"],
        conversation_title="One",
        source="ChatGPT",
        timestamp=now,
        snippet="right",
        text="right",
        score=0.9,
        match_type="semantic",
    )
    fused = reciprocal_rank_fusion([left], [right], limit=5)
    assert len(fused) == 1
    assert fused[0].message_id in {"m1", "m2"}


def test_tagged_fallback_prefers_recent_chunks(client: TestClient) -> None:
    _import_and_parse(client)
    items = client.get("/api/conversations").json()["items"]
    convo_id = items[0]["id"]
    source = items[0]["source"]
    old = datetime.now(timezone.utc) - timedelta(days=400)
    new = datetime.now(timezone.utc) - timedelta(days=2)
    db = get_session_factory()()
    try:
        db.add(
            MemoryChunk(
                conversation_id=convo_id,
                source=source,
                timestamp=old,
                text="oldest tagged chunk about nothing in particular",
                message_ids="[]",
            )
        )
        db.add(
            MemoryChunk(
                conversation_id=convo_id,
                source=source,
                timestamp=new,
                text="newest tagged chunk about nothing in particular",
                message_ids="[]",
            )
        )
        db.commit()
        hits = fallback_conversation_chunks(db, [convo_id], limit=8)
    finally:
        db.close()

    texts = [hit.text for hit in hits]
    assert "newest tagged chunk about nothing in particular" in texts
    assert texts.index("newest tagged chunk about nothing in particular") < texts.index(
        "oldest tagged chunk about nothing in particular"
    )
