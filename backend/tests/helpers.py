from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any


def chatgpt_conversation(
    *,
    conversation_id: str = "conv-1",
    title: str | None = "Grafana alert architecture",
    messages: list[tuple[str, str, str]] | None = None,
    create_time: float | None = 1_700_000_000,
    deleted: bool = False,
) -> dict:
    if messages is None:
        messages = [
            ("msg-user", "user", "Should we use Grafana for alerts?"),
            (
                "msg-asst",
                "assistant",
                "Yes. Use Grafana with Prometheus for monitoring and alerts.",
            ),
        ]

    mapping: dict = {
        "client-created-root": {
            "id": "client-created-root",
            "parent": None,
            "children": [],
            "message": None,
        }
    }
    parent = "client-created-root"
    last = parent
    for msg_id, role, text in messages:
        mapping[parent]["children"].append(msg_id)
        mapping[msg_id] = {
            "id": msg_id,
            "parent": parent,
            "children": [],
            "message": {
                "id": msg_id,
                "author": {"role": role},
                "content": {"content_type": "text", "parts": [text]},
                "create_time": (create_time or 0) + len(mapping),
            },
        }
        parent = msg_id
        last = msg_id

    payload = {
        "id": conversation_id,
        "conversation_id": conversation_id,
        "title": title,
        "create_time": create_time,
        "update_time": (create_time or 0) + 100 if create_time else None,
        "current_node": last,
        "mapping": mapping,
    }
    if deleted:
        payload["is_deleted"] = True
    return payload


def zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            archive.writestr(name, data)
    return buffer.getvalue()


def export_zip(conversations: list[dict], extra: dict[str, str] | None = None) -> bytes:
    files: dict[str, str | bytes] = {
        "conversations.json": json.dumps(conversations),
    }
    if extra:
        files.update(extra)
    return zip_bytes(files)


def write_export_dir(path: Path, conversations: list[dict]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "conversations.json").write_text(json.dumps(conversations), encoding="utf-8")
    return path


def share_html_for(conversation: dict[str, Any], *, legacy: bool = False) -> str:
    """Minimal ChatGPT share page wrapping a conversation payload."""
    if legacy:
        next_data = {
            "props": {
                "pageProps": {
                    "serverResponse": {"data": conversation},
                }
            }
        }
        return (
            "<!doctype html><html><body>"
            f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>'
            "</body></html>"
        )

    loader = [
        {},
        "loaderData",
        {
            "routes/share.$shareId.($action)": {
                "sharedConversationId": conversation.get("conversation_id")
                or conversation.get("id"),
                "serverResponse": {"data": conversation},
            }
        },
    ]
    argument = json.dumps(json.dumps(loader) + "\n")
    return (
        "<!doctype html><html><body>"
        f"<script>window.__reactRouterContext.streamController.enqueue({argument});</script>"
        "</body></html>"
    )
