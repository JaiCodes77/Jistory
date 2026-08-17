from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.imports.claude.share import (
    parse_share_html,
    parse_share_url,
    parsed_conversation_from_share,
)
from app.imports.validators import ImportValidationError
from tests.helpers import claude_conversation, claude_share_html_for, load_fixture_text


@pytest.mark.parametrize(
    "raw, expected_id",
    [
        (
            "https://claude.ai/share/fbe3711d-104f-4478-b1da-d5875282a971",
            "fbe3711d-104f-4478-b1da-d5875282a971",
        ),
        (
            "https://www.claude.ai/share/fbe3711d-104f-4478-b1da-d5875282a971",
            "fbe3711d-104f-4478-b1da-d5875282a971",
        ),
        ("claude.ai/share/abcde12345", "abcde12345"),
        ("abcde12345", "abcde12345"),
    ],
)
def test_parse_claude_share_url_accepts_public_links(raw: str, expected_id: str) -> None:
    canonical, share_id = parse_share_url(raw)
    assert share_id == expected_id
    assert canonical == f"https://claude.ai/share/{expected_id}"


@pytest.mark.parametrize(
    "raw",
    [
        "https://claude.ai/chat/fbe3711d-104f-4478-b1da-d5875282a971",
        "https://evil.example/share/abcde12345",
        "http://claude.ai/share/abcde12345",
        "https://claude.ai/api/chat_snapshots/abcde12345",
        "",
    ],
)
def test_parse_claude_share_url_rejects_unsafe_or_private_links(raw: str) -> None:
    with pytest.raises(ImportValidationError):
        parse_share_url(raw)


def test_private_chat_url_explains_share_step() -> None:
    with pytest.raises(ImportValidationError) as exc:
        parse_share_url("https://claude.ai/chat/fbe3711d-104f-4478-b1da-d5875282a971")
    assert exc.value.code == "private_conversation_url"
    assert "Share" in exc.value.message


def test_fixture_share_html_extracts_conversation() -> None:
    html = load_fixture_text("claude", "share.html")
    parsed = parsed_conversation_from_share(parse_share_html(html))
    assert parsed.external_id == "share-conv-1"
    assert parsed.title == "Grafana alert architecture"
    assert parsed.message_count == 2
    assert parsed.messages[0].role == "user"
    assert "Prometheus" in parsed.messages[1].content


def test_login_wall_html_fails_closed() -> None:
    html = load_fixture_text("claude", "private_login.html")
    with pytest.raises(ImportValidationError) as exc:
        parse_share_html(html)
    assert exc.value.code == "private_conversation_url"


def test_private_snapshot_html_fails_closed() -> None:
    html = load_fixture_text("claude", "private_share.html")
    with pytest.raises(ImportValidationError) as exc:
        parse_share_html(html)
    assert exc.value.code == "private_conversation_url"


def test_generated_share_html_roundtrip() -> None:
    raw = claude_conversation(conversation_id="from-share", public=True)
    parsed = parsed_conversation_from_share(parse_share_html(claude_share_html_for(raw)))
    assert parsed.external_id == "from-share"
    assert parsed.messages[0].role == "user"


def test_empty_assistant_placeholder_is_dropped() -> None:
    raw = claude_conversation(
        conversation_id="empty-asst",
        messages=[
            ("u1", "human", "Hello"),
            ("a0", "assistant", ""),
            ("a1", "assistant", "Hi there."),
        ],
        public=True,
    )
    raw["chat_messages"][1]["content"] = []
    parsed = parsed_conversation_from_share(parse_share_html(claude_share_html_for(raw)))
    assert [message.content for message in parsed.messages] == ["Hello", "Hi there."]


def test_claude_share_import_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    html = load_fixture_text("claude", "share.html")
    monkeypatch.setattr("app.imports.share_service.fetch_claude_html", lambda url: html)

    response = client.post(
        "/api/import/claude/share",
        json={"url": "https://claude.ai/share/from-share-id-ok"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["conversations"] == 1
    assert body["messages"] == 2

    listed = client.get("/api/conversations")
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["title"] == "Grafana alert architecture"
    assert listed.json()["items"][0]["source"] == "Claude"


def test_claude_share_import_rejects_private_url(client: TestClient) -> None:
    response = client.post(
        "/api/import/claude/share",
        json={"url": "https://claude.ai/chat/fbe3711d-104f-4478-b1da-d5875282a971"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "private_conversation_url"


def test_claude_share_import_rejects_login_wall(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = load_fixture_text("claude", "private_login.html")
    monkeypatch.setattr("app.imports.share_service.fetch_claude_html", lambda url: html)
    response = client.post(
        "/api/import/claude/share",
        json={"url": "https://claude.ai/share/private-share-xx"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "private_conversation_url"


def test_claude_share_js_shell_uses_snapshot_json(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.imports.share_service.fetch_claude_html",
        lambda url: "<!doctype html><html><body><div id='root'></div></body></html>",
    )
    monkeypatch.setattr(
        "app.imports.share_service.fetch_claude_snapshot",
        lambda share_id: claude_conversation(conversation_id="snap-conv", public=True),
    )
    response = client.post(
        "/api/import/claude/share",
        json={"url": "https://claude.ai/share/snap-share-id-ok"},
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/conversations").json()["items"][0]["source"] == "Claude"


def test_claude_share_import_is_idempotent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = claude_share_html_for(claude_conversation(conversation_id="same-share", public=True))
    monkeypatch.setattr("app.imports.share_service.fetch_claude_html", lambda url: html)

    first = client.post(
        "/api/import/claude/share",
        json={"url": "https://claude.ai/share/same-share-xx"},
    )
    second = client.post(
        "/api/import/claude/share",
        json={"url": "https://claude.ai/share/same-share-xx"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert client.get("/api/conversations").json()["total"] == 1
