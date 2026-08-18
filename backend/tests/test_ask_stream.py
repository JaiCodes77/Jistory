from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.ask.service import ask_stream
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_session_factory
from app.llm.base import ChatTurn, LLMProvider
from tests.helpers import chatgpt_conversation, export_zip


class StreamingLLM(LLMProvider):
    model_name = "stream-llm"

    def generate(self, *, system: str, prompt: str, history: list[ChatTurn]) -> str:
        return "Hello world"

    def generate_stream(self, *, system: str, prompt: str, history: list[ChatTurn]):
        yield "Hello "
        yield "world"


class BadKeyLLM(LLMProvider):
    model_name = "bad-key"

    def generate(self, *, system: str, prompt: str, history: list[ChatTurn]) -> str:
        raise AppError(
            "Gemini rejected the API key. Update it in Settings or your .env file.",
            code="invalid_api_key",
            status_code=400,
        )

    def generate_stream(self, *, system: str, prompt: str, history: list[ChatTurn]):
        raise AppError(
            "Gemini rejected the API key. Update it in Settings or your .env file.",
            code="invalid_api_key",
            status_code=400,
        )


def _seed(client: TestClient) -> None:
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
            )
        ]
    )
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    parsed = client.post(f"/api/import/{uploaded.json()['importId']}/parse")
    assert parsed.status_code == 200


def _parse_sse(raw: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        line = next((part[6:] for part in block.split("\n") if part.startswith("data: ")), None)
        if line:
            events.append(json.loads(line))
    return events


def test_ask_stream_yields_sources_then_text(client: TestClient) -> None:
    _seed(client)
    db = get_session_factory()()
    try:
        events = list(
            ask_stream(
                db,
                get_settings(),
                message="What conclusion did I reach about Grafana alerts?",
                conversation_id=None,
                llm=StreamingLLM(),
            )
        )
    finally:
        db.close()

    assert events
    assert events[0]["type"] == "sources"
    assert events[0]["retrieved"] >= 1
    assert events[0]["conversation_id"]
    assert events[0]["sources"]
    types = [event["type"] for event in events]
    assert "token" in types
    assert types[-1] == "done"
    text = "".join(event["text"] for event in events if event["type"] == "token")
    assert text == "Hello world"
    assert events[-1]["conversation_id"] == events[0]["conversation_id"]
    assert events[-1]["retrieved"] == events[0]["retrieved"]
    assert events[-1]["answer"] == "Hello world"


def test_ask_stream_http_sends_sse(client: TestClient, monkeypatch) -> None:
    _seed(client)
    monkeypatch.setattr("app.ask.service.require_llm_provider", lambda settings: StreamingLLM())
    with client.stream(
        "POST",
        "/api/ask/stream",
        json={"message": "What conclusion did I reach about Grafana alerts?"},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        events = _parse_sse(response.read().decode())

    assert events[0]["type"] == "sources"
    assert any(event["type"] == "token" for event in events)
    assert events[-1]["type"] == "done"


def test_ask_stream_maps_gemini_error_codes(client: TestClient) -> None:
    _seed(client)
    db = get_session_factory()()
    try:
        events = list(
            ask_stream(
                db,
                get_settings(),
                message="What conclusion did I reach about Grafana alerts?",
                conversation_id=None,
                llm=BadKeyLLM(),
            )
        )
    finally:
        db.close()

    assert events[0]["type"] == "sources"
    error = next(event for event in events if event["type"] == "error")
    assert error["code"] == "invalid_api_key"
    assert "traceback" not in error["error"].lower()


def test_ask_stream_missing_key_uses_existing_code(client: TestClient) -> None:
    _seed(client)
    db = get_session_factory()()
    try:
        events = list(
            ask_stream(
                db,
                get_settings(),
                message="What conclusion did I reach about Grafana alerts?",
                conversation_id=None,
            )
        )
    finally:
        db.close()
    error = next(event for event in events if event["type"] == "error")
    assert error["code"] == "missing_api_key"
