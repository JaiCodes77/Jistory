from __future__ import annotations

from fastapi.testclient import TestClient

from app.ask.service import ask
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.llm.base import ChatTurn, LLMProvider
from app.llm.gemini import map_gemini_exception
from tests.helpers import chatgpt_conversation, export_zip


class RecordingLLM(LLMProvider):
    model_name = "fake-llm"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.response = "You decided to use Grafana with Prometheus. [1]"

    def generate(self, *, system: str, prompt: str, history: list[ChatTurn]) -> str:
        self.calls.append({"system": system, "prompt": prompt, "history": history})
        return self.response


class ExplodingLLM(LLMProvider):
    model_name = "explode"

    def generate(self, *, system: str, prompt: str, history: list[ChatTurn]) -> str:
        raise AssertionError("LLM should not be called when retrieval is empty")


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
                    ("u2", "user", "That is the decision then."),
                ],
            )
        ]
    )
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    parsed = client.post(f"/api/import/{uploaded.json()['importId']}/parse")
    assert parsed.status_code == 200


def test_ask_passes_retrieved_context_and_citations(client: TestClient) -> None:
    _seed(client)
    llm = RecordingLLM()
    db = get_session_factory()()
    try:
        result = ask(
            db,
            get_settings(),
            message="What conclusion did I reach about Grafana alerts?",
            conversation_id=None,
            llm=llm,
        )
    finally:
        db.close()

    assert llm.calls, "expected the LLM to receive retrieved context"
    assert "Prometheus" in llm.calls[0]["prompt"]
    assert "CONVERSATION HISTORY" in llm.calls[0]["prompt"]
    assert result.sources
    assert result.sources[0].title == "Grafana alert architecture"
    assert result.sources[0].conversation_id
    assert result.answer == llm.response


def test_empty_retrieval_does_not_call_llm(client: TestClient) -> None:
    _seed(client)
    db = get_session_factory()()
    try:
        result = ask(
            db,
            get_settings(),
            message="xyzzyplugh completely unknown topic",
            conversation_id=None,
            llm=ExplodingLLM(),
        )
    finally:
        db.close()

    assert result.sources == []
    assert "could not find" in result.answer.lower()


def test_ask_without_memories(client: TestClient) -> None:
    db = get_session_factory()()
    try:
        result = ask(
            db,
            get_settings(),
            message="What did I decide?",
            conversation_id=None,
            llm=ExplodingLLM(),
        )
    finally:
        db.close()
    assert "memories yet" in result.answer.lower()
    assert result.sources == []


def test_gemini_errors_are_user_facing() -> None:
    invalid = map_gemini_exception(RuntimeError("API key not valid. Please pass a valid API key."))
    assert invalid.code == "invalid_api_key"
    assert "traceback" not in invalid.message.lower()
    timeout = map_gemini_exception(TimeoutError("deadline exceeded"))
    assert timeout.code == "llm_timeout"
    assert timeout.status_code == 504


def test_ask_without_api_key_returns_user_error(client: TestClient) -> None:
    _seed(client)
    response = client.post("/api/ask", json={"message": "What conclusion did I reach about Grafana alerts?"})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "missing_api_key"
    assert "GEMINI_API_KEY" in body["error"]
    assert "traceback" not in body["error"].lower()


def test_settings_does_not_expose_api_key(client: TestClient) -> None:
    patched = client.patch(
        "/api/settings",
        json={"gemini_api_key": "secret-key-value", "retrieval_limit": 6, "gemini_model": "gemini-2.5-flash"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert "secret-key-value" not in str(body)
    assert body["api_key_configured"] is True
    assert body["retrieval_limit"] == 6
    assert body["gemini_model"] == "gemini-2.5-flash"
