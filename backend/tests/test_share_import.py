from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.imports.chatgpt.share import (
    parse_share_html,
    parse_share_url,
    parsed_conversation_from_share,
)
from app.imports.validators import ImportValidationError
from tests.helpers import chatgpt_conversation, share_html_for


@pytest.mark.parametrize(
    "raw, expected_id",
    [
        ("https://chatgpt.com/share/69a0aec2-1cfc-8007-a2a2-d1909bafec82", "69a0aec2-1cfc-8007-a2a2-d1909bafec82"),
        ("https://chatgpt.com/share/e/69a0aec2-1cfc-8007-a2a2-d1909bafec82", "69a0aec2-1cfc-8007-a2a2-d1909bafec82"),
        ("https://chat.openai.com/share/abcde12345", "abcde12345"),
        ("chatgpt.com/share/abcde12345", "abcde12345"),
        ("abcde12345", "abcde12345"),
    ],
)
def test_parse_share_url_accepts_public_links(raw: str, expected_id: str) -> None:
    canonical, share_id = parse_share_url(raw)
    assert share_id == expected_id
    assert canonical == f"https://chatgpt.com/share/{expected_id}"


@pytest.mark.parametrize(
    "raw",
    [
        "https://chatgpt.com/c/69a0aec2-1cfc-8007-a2a2-d1909bafec82",
        "https://evil.example/share/abcde12345",
        "http://chatgpt.com/share/abcde12345",
        "https://chatgpt.com/backend-api/share/abcde12345",
        "",
    ],
)
def test_parse_share_url_rejects_unsafe_or_private_links(raw: str) -> None:
    with pytest.raises(ImportValidationError):
        parse_share_url(raw)


def test_private_chat_url_explains_share_step() -> None:
    with pytest.raises(ImportValidationError) as exc:
        parse_share_url("https://chatgpt.com/c/69a0aec2-1cfc-8007-a2a2-d1909bafec82")
    assert exc.value.code == "private_conversation_url"
    assert "Share" in exc.value.message


def test_parse_modern_share_html() -> None:
    raw = chatgpt_conversation(conversation_id="share-conv")
    raw["backing_conversation_id"] = "original-conv"
    html = share_html_for(raw)
    data = parse_share_html(html)
    parsed = parsed_conversation_from_share(data)
    assert parsed.external_id == "original-conv"
    assert parsed.title == "Grafana alert architecture"
    assert parsed.message_count == 2
    assert parsed.messages[0].role == "user"


def test_parse_legacy_share_html() -> None:
    raw = chatgpt_conversation(conversation_id="legacy-conv")
    html = share_html_for(raw, legacy=True)
    parsed = parsed_conversation_from_share(parse_share_html(html))
    assert parsed.external_id == "legacy-conv"
    assert parsed.message_count == 2


def test_hidden_system_messages_are_dropped() -> None:
    raw = chatgpt_conversation(
        conversation_id="hidden-sys",
        messages=[
            ("s1", "system", ""),
            ("u1", "user", "Remember Redis."),
            ("a1", "assistant", "Redis is the cache."),
        ],
    )
    raw["mapping"]["s1"]["message"]["metadata"] = {
        "is_visually_hidden_from_conversation": True
    }
    parsed = parsed_conversation_from_share(parse_share_html(share_html_for(raw)))
    roles = [message.role for message in parsed.messages]
    assert roles == ["user", "assistant"]


def test_empty_assistant_placeholder_is_dropped() -> None:
    raw = chatgpt_conversation(
        conversation_id="empty-asst",
        messages=[
            ("u1", "user", "Hello"),
            ("a0", "assistant", ""),
            ("a1", "assistant", "Hi there."),
        ],
    )
    parsed = parsed_conversation_from_share(parse_share_html(share_html_for(raw)))
    assert [message.content for message in parsed.messages] == ["Hello", "Hi there."]


def test_share_import_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    html = share_html_for(chatgpt_conversation(conversation_id="from-share"))
    monkeypatch.setattr("app.imports.share_service.fetch_share_html", lambda url: html)

    response = client.post(
        "/api/import/chatgpt/share",
        json={"url": "https://chatgpt.com/share/from-share-id-ok"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["conversations"] == 1
    assert body["messages"] == 2

    listed = client.get("/api/conversations")
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["title"] == "Grafana alert architecture"


def test_share_import_rejects_private_url(client: TestClient) -> None:
    response = client.post(
        "/api/import/chatgpt/share",
        json={"url": "https://chatgpt.com/c/69a0aec2-1cfc-8007-a2a2-d1909bafec82"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "private_conversation_url"


def test_share_import_is_idempotent(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    html = share_html_for(chatgpt_conversation(conversation_id="same-share"))
    monkeypatch.setattr("app.imports.share_service.fetch_share_html", lambda url: html)

    first = client.post(
        "/api/import/chatgpt/share",
        json={"url": "https://chatgpt.com/share/same-share-xx"},
    )
    second = client.post(
        "/api/import/chatgpt/share",
        json={"url": "https://chatgpt.com/share/same-share-xx"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert client.get("/api/conversations").json()["total"] == 1
