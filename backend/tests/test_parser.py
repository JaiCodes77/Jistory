from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.imports.chatgpt.parser import parse_chatgpt_export, parse_conversation_node
from tests.helpers import chatgpt_conversation, export_zip, write_export_dir


def test_normal_conversation(tmp_path: Path) -> None:
    write_export_dir(tmp_path, [chatgpt_conversation()])
    result = parse_chatgpt_export(tmp_path)
    assert result.skipped == 0
    assert len(result.conversations) == 1
    convo = result.conversations[0]
    assert convo.title == "Grafana alert architecture"
    assert convo.message_count == 2
    assert convo.messages[0].role == "user"
    assert "Grafana" in convo.messages[1].content


def test_empty_conversation(tmp_path: Path) -> None:
    raw = chatgpt_conversation(conversation_id="empty", title="Empty", messages=[])
    write_export_dir(tmp_path, [raw])
    result = parse_chatgpt_export(tmp_path)
    assert len(result.conversations) == 1
    assert result.conversations[0].message_count == 0


def test_malformed_message_is_skipped(tmp_path: Path) -> None:
    raw = chatgpt_conversation(conversation_id="bad")
    raw["mapping"]["msg-asst"]["message"] = "not-a-dict"
    write_export_dir(tmp_path, [raw])
    result = parse_chatgpt_export(tmp_path)
    assert len(result.conversations) == 1
    assert result.conversations[0].message_count == 1


def test_missing_timestamp(tmp_path: Path) -> None:
    raw = chatgpt_conversation(conversation_id="no-time", create_time=None)
    for node in raw["mapping"].values():
        if isinstance(node.get("message"), dict):
            node["message"]["create_time"] = None
    write_export_dir(tmp_path, [raw])
    result = parse_chatgpt_export(tmp_path)
    convo = result.conversations[0]
    assert convo.created_at is None
    assert all(message.created_at is None for message in convo.messages)


def test_deleted_conversation_skipped(tmp_path: Path) -> None:
    write_export_dir(
        tmp_path,
        [chatgpt_conversation(conversation_id="gone", deleted=True)],
    )
    result = parse_chatgpt_export(tmp_path)
    assert result.conversations == []
    assert result.skipped == 1


def test_multi_message_and_roles(tmp_path: Path) -> None:
    raw = chatgpt_conversation(
        conversation_id="multi",
        messages=[
            ("s1", "system", "You are helpful."),
            ("u1", "user", "Use Redis for caching."),
            ("a1", "assistant", "Agreed, Redis is the right cache."),
            ("t1", "tool", '{"ok": true}'),
        ],
    )
    write_export_dir(tmp_path, [raw])
    result = parse_chatgpt_export(tmp_path)
    roles = [m.role for m in result.conversations[0].messages]
    assert roles == ["system", "user", "assistant", "tool"]


def test_malformed_root_node_returns_none() -> None:
    assert parse_conversation_node("nope") is None
    assert parse_conversation_node({"title": "missing id"}) is None


def test_duplicate_import_does_not_duplicate_conversations(client: TestClient) -> None:
    payload = export_zip(
        [
            chatgpt_conversation(conversation_id="same-conv"),
            chatgpt_conversation(conversation_id="same-conv-2", title="Redis caching"),
        ]
    )

    first = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    second = client.post("/api/import/chatgpt", files={"file": ("b.zip", payload, "application/zip")})
    assert first.status_code == 200
    assert second.status_code == 200

    parsed_a = client.post(f"/api/import/{first.json()['importId']}/parse")
    parsed_b = client.post(f"/api/import/{second.json()['importId']}/parse")
    assert parsed_a.status_code == 200
    assert parsed_b.status_code == 200
    assert parsed_a.json()["conversations"] == 2
    assert parsed_b.json()["conversations"] == 2

    listed = client.get("/api/conversations")
    assert listed.status_code == 200
    assert listed.json()["total"] == 2


def test_reparse_same_job_is_idempotent(client: TestClient) -> None:
    payload = export_zip([chatgpt_conversation(conversation_id="once")])
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    import_id = uploaded.json()["importId"]
    first = client.post(f"/api/import/{import_id}/parse")
    second = client.post(f"/api/import/{import_id}/parse")
    assert first.json()["conversations"] == 1
    assert second.json()["conversations"] == 1
    assert client.get("/api/conversations").json()["total"] == 1


def test_parse_response_shape(client: TestClient) -> None:
    payload = export_zip([chatgpt_conversation()])
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    parsed = client.post(f"/api/import/{uploaded.json()['importId']}/parse")
    body = parsed.json()
    assert body["success"] is True
    assert body["conversations"] == 1
    assert body["messages"] == 2
    assert "elapsed_ms" in body
    assert body["status"] == "completed"
