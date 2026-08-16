"""Import a single public ChatGPT share page (chatgpt.com/share/...)."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.imports.chatgpt.content import extract_message_text
from app.imports.chatgpt.parser import parse_conversation_node
from app.imports.parsers.base import ParsedConversation
from app.imports.validators import ImportValidationError

ALLOWED_SHARE_HOSTS = frozenset(
    {
        "chatgpt.com",
        "www.chatgpt.com",
        "chat.openai.com",
        "www.chat.openai.com",
    }
)
SHARE_FETCH_TIMEOUT_S = 20
MAX_SHARE_HTML_BYTES = 12 * 1024 * 1024
_SHARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_ENQUEUE_CALL = "streamController.enqueue("
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://chatgpt.com/",
}


class _HostRestrictedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        parsed = urlparse(newurl)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host not in ALLOWED_SHARE_HOSTS:
            raise ImportValidationError(
                "The share link redirected to an unexpected host and was blocked.",
                code="invalid_share_url",
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def parse_share_url(raw: str) -> tuple[str, str]:
    """Return (canonical https share URL, share id)."""
    text = unescape(raw or "").strip()
    if not text:
        raise ImportValidationError(
            "Paste a ChatGPT share link first.",
            code="invalid_share_url",
        )

    if "://" not in text and "/" not in text and _SHARE_ID_RE.fullmatch(text):
        text = f"https://chatgpt.com/share/{text}"
    elif text.lower().startswith("chatgpt.com/") or text.lower().startswith("chat.openai.com/"):
        text = f"https://{text}"

    try:
        parsed = urlparse(text)
    except ValueError as exc:
        raise ImportValidationError(
            "That does not look like a ChatGPT share link.",
            code="invalid_share_url",
        ) from exc

    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    segments = [part for part in path.split("/") if part]

    if host in ALLOWED_SHARE_HOSTS and segments[:1] == ["c"]:
        raise ImportValidationError(
            "That is a private ChatGPT chat URL. Open the chat, click Share, "
            "copy the public chatgpt.com/share/... link, then paste that here.",
            code="private_conversation_url",
        )

    if parsed.scheme and parsed.scheme != "https":
        raise ImportValidationError(
            "Share links must start with https://chatgpt.com/share/...",
            code="invalid_share_url",
        )

    if host not in ALLOWED_SHARE_HOSTS:
        raise ImportValidationError(
            "Only public ChatGPT share links are supported "
            "(https://chatgpt.com/share/...).",
            code="invalid_share_url",
        )

    if not segments or segments[0] != "share":
        raise ImportValidationError(
            "That does not look like a ChatGPT share link. "
            "In ChatGPT, click Share → Copy link, then paste it here.",
            code="invalid_share_url",
        )

    share_id = segments[2] if len(segments) >= 3 and segments[1] == "e" else segments[1] if len(segments) >= 2 else ""
    if share_id in {"e", "c"} and len(segments) >= 3:
        share_id = segments[2]
    if not share_id or not _SHARE_ID_RE.fullmatch(share_id):
        raise ImportValidationError(
            "That share link is missing a conversation id.",
            code="invalid_share_url",
        )

    canonical = f"https://chatgpt.com/share/{share_id}"
    return canonical, share_id


def fetch_share_html(url: str) -> str:
    canonical, _share_id = parse_share_url(url)
    request = Request(canonical, headers=_BROWSER_HEADERS, method="GET")
    opener = build_opener(_HostRestrictedRedirects)
    try:
        with opener.open(request, timeout=SHARE_FETCH_TIMEOUT_S) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SHARE_HTML_BYTES:
                    raise ImportValidationError(
                        "The share page was larger than expected and was not imported.",
                        code="share_fetch_failed",
                    )
                chunks.append(chunk)
            return b"".join(chunks).decode(charset, errors="replace")
    except ImportValidationError:
        raise
    except HTTPError as exc:
        if exc.code == 404:
            raise ImportValidationError(
                "This share link was not found. It may have been unpublished.",
                code="share_not_found",
            ) from exc
        if exc.code in {401, 403}:
            raise ImportValidationError(
                "ChatGPT blocked the share page. Make sure the chat is shared "
                "publicly, then try again.",
                code="share_fetch_failed",
            ) from exc
        raise ImportValidationError(
            "Could not download that share link. Please try again.",
            code="share_fetch_failed",
        ) from exc
    except TimeoutError as exc:
        raise ImportValidationError(
            "Timed out while downloading the share link.",
            code="share_fetch_failed",
        ) from exc
    except URLError as exc:
        raise ImportValidationError(
            "Could not reach ChatGPT to download that share link.",
            code="share_fetch_failed",
        ) from exc


def parse_share_html(html: str) -> dict[str, Any]:
    data = _parse_modern_share(html)
    if data is None:
        data = _parse_legacy_share(html)
    if not isinstance(data, dict):
        raise ImportValidationError(
            "Could not read the conversation from that share page. "
            "Make sure the link is public and copied from Share.",
            code="share_parse_failed",
        )
    return _normalize_share_payload(data)


def parsed_conversation_from_share(data: dict[str, Any]) -> ParsedConversation:
    parsed = parse_conversation_node(data)
    if parsed is None:
        raise ImportValidationError(
            "That share link does not contain any messages to import.",
            code="share_parse_failed",
        )
    parsed.messages = [
        message for message in parsed.messages if (message.content or "").strip()
    ]
    for index, message in enumerate(parsed.messages):
        message.sequence_number = index
        if index == 0:
            message.parent_external_id = None
    if not parsed.messages:
        raise ImportValidationError(
            "That share link does not contain any messages to import.",
            code="share_parse_failed",
        )
    return parsed


def _normalize_share_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    backing = payload.get("backing_conversation_id")
    if isinstance(backing, str) and backing.strip():
        payload["id"] = backing.strip()
        payload["conversation_id"] = backing.strip()

    mapping = payload.get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        mapping = _mapping_from_linear(payload.get("linear_conversation"))
        payload["mapping"] = mapping

    if isinstance(mapping, dict):
        for node in mapping.values():
            if not isinstance(node, dict):
                continue
            message = node.get("message")
            if not isinstance(message, dict):
                continue
            metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
            if metadata.get("is_visually_hidden_from_conversation"):
                node["message"] = None
                continue
            if not extract_message_text(message):
                node["message"] = None

    return payload


def _mapping_from_linear(linear: Any) -> dict[str, Any]:
    if not isinstance(linear, list):
        return {}
    mapping: dict[str, Any] = {}
    parent: str | None = None
    for entry in linear:
        if not isinstance(entry, dict):
            continue
        node_id = entry.get("id")
        if not node_id:
            continue
        node_id = str(node_id)
        mapping[node_id] = {
            "id": node_id,
            "parent": entry.get("parent") or parent,
            "children": entry.get("children") or [],
            "message": entry.get("message"),
        }
        parent = node_id
    return mapping


def _parse_modern_share(html: str) -> dict[str, Any] | None:
    loader = _extract_loader_payload(html)
    if not loader:
        return None
    decoded = _decode_loader(loader)
    return _find_share_data(decoded)


def _parse_legacy_share(html: str) -> dict[str, Any] | None:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    props = payload.get("props") if isinstance(payload.get("props"), dict) else {}
    page_props = props.get("pageProps") if isinstance(props.get("pageProps"), dict) else {}
    server = (
        page_props.get("serverResponse")
        if isinstance(page_props.get("serverResponse"), dict)
        else {}
    )
    data = server.get("data")
    return data if isinstance(data, dict) else None


def _find_share_data(decoded: dict[str, Any]) -> dict[str, Any] | None:
    loader_data = decoded.get("loaderData")
    if isinstance(loader_data, dict):
        for value in loader_data.values():
            if not isinstance(value, dict):
                continue
            server = value.get("serverResponse")
            if isinstance(server, dict) and isinstance(server.get("data"), dict):
                return server["data"]
    server = decoded.get("serverResponse")
    if isinstance(server, dict) and isinstance(server.get("data"), dict):
        return server["data"]
    return None


def _extract_loader_payload(html: str) -> list[Any] | None:
    for script in _SCRIPT_RE.findall(html):
        if _ENQUEUE_CALL not in script:
            continue
        start = 0
        while True:
            anchor = script.find(_ENQUEUE_CALL, start)
            if anchor < 0:
                break
            argument, end = _find_call_argument(script, anchor + len(_ENQUEUE_CALL))
            if argument is None or end is None:
                break
            payload = _parse_enqueued_loader(argument)
            if payload:
                return payload
            start = end
    return None


def _find_call_argument(text: str, start: int) -> tuple[str | None, int | None]:
    quote: str | None = None
    escaped = False
    depth = 1
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index].strip(), index + 1
    return None, None


def _parse_enqueued_loader(argument: str) -> list[Any] | None:
    stripped = argument.strip()
    while stripped.startswith("(") and stripped.endswith(")"):
        stripped = stripped[1:-1].strip()
    chunk: Any = stripped
    if stripped.startswith('"'):
        try:
            chunk = json.loads(stripped)
        except json.JSONDecodeError:
            return None
    if isinstance(chunk, str):
        trimmed = chunk.strip()
        if not trimmed.startswith("["):
            return None
        try:
            parsed = json.loads(trimmed)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    if isinstance(chunk, list):
        return chunk
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _decode_loader(loader: list[Any]) -> dict[str, Any]:
    cache: dict[int, Any] = {}

    def decode_key(raw: Any) -> Any:
        if isinstance(raw, str) and re.fullmatch(r"_\d+", raw):
            index = int(raw[1:])
            candidate = loader[index] if 0 <= index < len(loader) else None
            if isinstance(candidate, str):
                return candidate
        return raw

    def resolve(value: Any) -> Any:
        if type(value) is int:
            if value in cache:
                return cache[value]
            if value < 0 or value >= len(loader):
                return value
            cache[value] = None
            resolved = resolve(loader[value])
            cache[value] = resolved
            return resolved
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, dict):
            return {decode_key(key): resolve(item) for key, item in value.items()}
        return value

    decoded: dict[str, Any] = {}
    for index in range(1, max(len(loader) - 1, 0), 2):
        key = loader[index]
        if isinstance(key, str) and key not in decoded:
            decoded[key] = resolve(loader[index + 1])
    return decoded
