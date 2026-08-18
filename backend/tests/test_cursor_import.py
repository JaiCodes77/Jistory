from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.ask.service import ask
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.imports.cursor.parser import parse_cursor_import
from app.imports.parsers import get_parser
from app.llm.base import ChatTurn, LLMProvider
from tests.helpers import write_cursor_transcript, write_cursor_vscdb


class RecordingLLM(LLMProvider):
    model_name = "fake-llm"

    def generate(self, *, system: str, prompt: str, history: list[ChatTurn]) -> str:
        return "Stay in SQLite. [1]"


def test_cursor_parser_is_registered() -> None:
    parser = get_parser("Cursor")
    assert parser.source == "Cursor"
    assert get_parser("cursor").source == "Cursor"


def test_cursor_vscdb_parse_skips_empty_tool_bubbles(tmp_path: Path) -> None:
    db_path = write_cursor_vscdb(tmp_path / "state.vscdb")
    result = parse_cursor_import(db_path.parent)
    assert len(result.conversations) == 1
    convo = result.conversations[0]
    assert convo.external_id == "composer-1"
    assert convo.title == "sqlite-vec vs FAISS"
    roles = [message.role for message in convo.messages]
    assert roles == ["user", "assistant"]
    assert "sqlite-vec" in convo.messages[0].content
    assert not any(message.role == "tool" for message in convo.messages)


def test_cursor_skips_tool_only_composer(tmp_path: Path) -> None:
    write_cursor_vscdb(
        tmp_path / "state.vscdb",
        composer_id="tool-only",
        title="noise",
        bubbles=[
            {
                "bubbleId": "b-tool",
                "type": 3,
                "toolFormerData": {"tool": "read"},
                "text": "",
            }
        ],
    )
    result = parse_cursor_import(tmp_path)
    assert result.conversations == []
    assert result.skipped == 1


def test_cursor_json_transcript_parse(tmp_path: Path) -> None:
    write_cursor_transcript(tmp_path / "chat.json")
    result = parse_cursor_import(tmp_path)
    assert len(result.conversations) == 1
    assert result.conversations[0].external_id == "composer-json-1"
    assert result.conversations[0].messages[0].role == "user"


def test_cursor_import_from_path_parses_and_indexes(client: TestClient, tmp_path: Path) -> None:
    db_path = write_cursor_vscdb(tmp_path / "state.vscdb")
    response = client.post("/api/import/cursor", json={"path": str(db_path)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["conversations"] == 1
    assert body["messages"] == 2
    assert body["skipped"] == 0

    listed = client.get("/api/conversations")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert listed.json()["total"] == 1
    assert items[0]["source"] == "Cursor"
    assert items[0]["title"] == "sqlite-vec vs FAISS"


def test_cursor_reimport_is_idempotent_on_source_external_id(
    client: TestClient, tmp_path: Path
) -> None:
    db_path = write_cursor_vscdb(tmp_path / "state.vscdb")
    first = client.post("/api/import/cursor", json={"path": str(db_path)})
    second = client.post("/api/import/cursor", json={"path": str(db_path)})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["conversations"] == 1
    assert second.json()["conversations"] == 1
    listed = client.get("/api/conversations")
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["source"] == "Cursor"


def test_cursor_fts_hit(client: TestClient, tmp_path: Path) -> None:
    db_path = write_cursor_vscdb(tmp_path / "state.vscdb")
    imported = client.post("/api/import/cursor", json={"path": str(db_path)})
    assert imported.status_code == 200
    search = client.get("/api/search", params={"q": "sqlite-vec", "mode": "keyword"})
    assert search.status_code == 200
    hits = search.json()["results"]
    assert hits
    assert hits[0]["source"] == "Cursor"
    assert "sqlite-vec" in hits[0]["snippet"].lower() or "sqlite" in hits[0]["snippet"].lower()


def test_ask_source_label_is_cursor(client: TestClient, tmp_path: Path) -> None:
    db_path = write_cursor_vscdb(tmp_path / "state.vscdb")
    imported = client.post("/api/import/cursor", json={"path": str(db_path)})
    assert imported.status_code == 200
    llm = RecordingLLM()
    db = get_session_factory()()
    try:
        result = ask(
            db,
            get_settings(),
            message="What did I decide about sqlite-vec for Cursor embeddings?",
            conversation_id=None,
            llm=llm,
        )
    finally:
        db.close()
    assert result.sources
    assert result.sources[0].source == "Cursor"


def test_cursor_upload_file(client: TestClient, tmp_path: Path) -> None:
    db_path = write_cursor_vscdb(tmp_path / "state.vscdb")
    response = client.post(
        "/api/import/cursor/upload",
        files={"file": ("state.vscdb", db_path.read_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["conversations"] == 1
    listed = client.get("/api/conversations")
    assert listed.json()["items"][0]["source"] == "Cursor"


def test_cursor_uses_settings_path_when_body_omits_path(
    client: TestClient, tmp_path: Path
) -> None:
    db_path = write_cursor_vscdb(tmp_path / "state.vscdb")
    saved = client.patch("/api/settings", json={"cursor_import_path": str(db_path)})
    assert saved.status_code == 200
    assert saved.json()["cursor_import_path"] == str(db_path)
    response = client.post("/api/import/cursor", json={})
    assert response.status_code == 200, response.text
    assert response.json()["conversations"] == 1


def test_cursor_rejects_share_urls(client: TestClient) -> None:
    response = client.post(
        "/api/import/cursor",
        json={"path": "https://cursor.com/share/abc"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "cursor_share_unsupported"


def test_cursor_does_not_scan_home_by_default(client: TestClient) -> None:
    response = client.post("/api/import/cursor", json={})
    assert response.status_code == 400
    assert response.json()["code"] == "missing_path"
    listed = client.get("/api/conversations")
    assert listed.json()["total"] == 0


def test_cursor_folder_import(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "cursor-export"
    write_cursor_vscdb(folder / "state.vscdb")
    response = client.post("/api/import/cursor", json={"path": str(folder)})
    assert response.status_code == 200, response.text
    assert response.json()["conversations"] == 1
