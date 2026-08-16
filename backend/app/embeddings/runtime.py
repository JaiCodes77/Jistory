from __future__ import annotations

import threading

_lock = threading.Lock()
_state = {
    "status": "idle",
    "detail": "Embedding model has not been loaded yet.",
}


def set_embedding_status(status: str, detail: str = "") -> None:
    with _lock:
        _state["status"] = status
        if detail:
            _state["detail"] = detail
        elif status == "idle":
            _state["detail"] = "Embedding model has not been loaded yet."
        elif status == "downloading":
            _state["detail"] = "Downloading the local embedding model (first run)…"
        elif status == "ready":
            _state["detail"] = "Local embedding model is ready."
        elif status == "unavailable":
            _state["detail"] = "Local embeddings are unavailable."
        elif status == "hash":
            _state["detail"] = "Using test hash embeddings."


def get_embedding_status() -> dict[str, str]:
    with _lock:
        return dict(_state)
