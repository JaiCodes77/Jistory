from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.imports.claude.parser import parse_claude_export, parse_conversation
from app.imports.parsers import get_parser
from app.imports.validators import ImportValidationError
from tests.helpers import (
    chatgpt_conversation,
    claude_conversation,
    claude_export_zip,
    load_fixture_json,
    write_claude_export_dir,
)


def test_claude_parser_is_registered() -> None:
    parser = get_parser("Claude")
    assert parser.source == "Claude"
    assert get_parser("claude").source == "Claude"


def test_fixture_conversations_parse(tmp_path: Path) -> None:
    payload = load_fixture_json("claude", "conversations.json")
    write_claude_export_dir(tmp_path, payload)
    result = parse_claude_export(tmp_path)
    assert result.skipped == 0
    assert len(result.conversations) == 1
    convo = result.conversations[0]
    assert convo.title == "Postgres vs MongoDB for metrics"
    assert convo.message_count == 2
    assert convo.messages[0].role == "user"
    assert convo.messages[1].role == "assistant"
    assert "Postgres" in convo.messages[1].content
    assert "thinking" not in convo.messages[1].content.lower()


def test_human_role_maps_to_user(tmp_path: Path) -> None:
    write_claude_export_dir(tmp_path, [claude_conversation()])
    result = parse_claude_export(tmp_path)
    assert [message.role for message in result.conversations[0].messages] == ["user", "assistant"]


def test_content_blocks_used_when_text_empty() -> None:
    parsed = parse_conversation(
        {
            "uuid": "c1",
            "name": "Blocks",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "sender": "assistant",
                    "text": "",
                    "content": [{"type": "text", "text": "Hello from a content block."}],
                }
            ],
        }
    )
    assert parsed is not None
    assert parsed.messages[0].content == "Hello from a content block."


def test_deleted_conversation_skipped(tmp_path: Path) -> None:
    write_claude_export_dir(
        tmp_path,
        [claude_conversation(conversation_id="gone", deleted=True)],
    )
    result = parse_claude_export(tmp_path)
    assert result.conversations == []
    assert result.skipped == 1


def test_chatgpt_zip_is_rejected_as_claude(tmp_path: Path) -> None:
    write_claude_export_dir(tmp_path, [chatgpt_conversation()])
    with pytest.raises(ImportValidationError) as exc:
        parse_claude_export(tmp_path)
    assert exc.value.code == "wrong_export_format"


def test_malformed_message_is_skipped(tmp_path: Path) -> None:
    raw = claude_conversation(conversation_id="bad")
    raw["chat_messages"].append("not-a-dict")
    write_claude_export_dir(tmp_path, [raw])
    result = parse_claude_export(tmp_path)
    assert len(result.conversations) == 1
    assert result.conversations[0].message_count == 2


def test_missing_timestamp(tmp_path: Path) -> None:
    raw = claude_conversation(conversation_id="no-time", created_at=None)
    write_claude_export_dir(tmp_path, [raw])
    result = parse_claude_export(tmp_path)
    convo = result.conversations[0]
    assert convo.created_at is None
    assert all(message.created_at is None for message in convo.messages)


def test_duplicate_claude_import_does_not_duplicate(client: TestClient) -> None:
    payload = claude_export_zip(
        [
            claude_conversation(conversation_id="same-conv"),
            claude_conversation(conversation_id="same-conv-2", title="Redis caching"),
        ]
    )
    first = client.post("/api/import/claude", files={"file": ("a.zip", payload, "application/zip")})
    second = client.post("/api/import/claude", files={"file": ("b.zip", payload, "application/zip")})
    assert first.status_code == 200
    assert second.status_code == 200

    parsed_a = client.post(f"/api/import/{first.json()['importId']}/parse")
    parsed_b = client.post(f"/api/import/{second.json()['importId']}/parse")
    assert parsed_a.status_code == 200
    assert parsed_b.status_code == 200
    assert parsed_a.json()["conversations"] == 2
    assert parsed_b.json()["conversations"] == 2
    listed = client.get("/api/conversations")
    assert listed.json()["total"] == 2
    assert listed.json()["items"][0]["source"] == "Claude"
