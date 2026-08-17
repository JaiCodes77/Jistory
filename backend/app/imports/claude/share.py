"""Import a single public Claude share page (claude.ai/share/...)."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.imports.claude.content import extract_message_text
from app.imports.claude.parser import parse_conversation
from app.imports.parsers.base import ParsedConversation
from app.imports.validators import ImportValidationError

ALLOWED_SHARE_HOSTS = frozenset(
    {
        "claude.ai",
        "www.claude.ai",
    }
)
SHARE_FETCH_TIMEOUT_S = 20
MAX_SHARE_HTML_BYTES = 12 * 1024 * 1024
_SHARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_JSON_SCRIPT_RE = re.compile(
    r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_LOGIN_MARKERS = (
    "log in to claude",
    "sign in to claude",
    "log in to continue",
    "sign in to continue",
    "you need to sign in",
    "you must be logged in",
    "must be signed in",
    "this conversation is private",
    "this share is private",
    "this share is no longer available",
    "you don't have access",
    "you do not have access",
    'href="/login"',
    'href="/login?',
    "/login?returnto=",
)
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://claude.ai/",
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
            "Paste a Claude share link first.",
            code="invalid_share_url",
        )

    if "://" not in text and "/" not in text and _SHARE_ID_RE.fullmatch(text):
        text = f"https://claude.ai/share/{text}"
    elif text.lower().startswith("claude.ai/") or text.lower().startswith("www.claude.ai/"):
        text = f"https://{text}"

    try:
        parsed = urlparse(text)
    except ValueError as exc:
        raise ImportValidationError(
            "That does not look like a Claude share link.",
            code="invalid_share_url",
        ) from exc

    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    segments = [part for part in path.split("/") if part]

    if host in ALLOWED_SHARE_HOSTS and segments[:1] == ["chat"]:
        raise ImportValidationError(
            "That is a private Claude chat URL. Open the chat, click Share, "
            "copy the public claude.ai/share/... link, then paste that here.",
            code="private_conversation_url",
        )

    if parsed.scheme and parsed.scheme != "https":
        raise ImportValidationError(
            "Share links must start with https://claude.ai/share/...",
            code="invalid_share_url",
        )

    if host not in ALLOWED_SHARE_HOSTS:
        raise ImportValidationError(
            "Only public Claude share links are supported "
            "(https://claude.ai/share/...).",
            code="invalid_share_url",
        )

    if not segments or segments[0] != "share":
        raise ImportValidationError(
            "That does not look like a Claude share link. "
            "In Claude, click Share → Copy link, then paste it here.",
            code="invalid_share_url",
        )

    share_id = segments[1] if len(segments) >= 2 else ""
    if not share_id or not _SHARE_ID_RE.fullmatch(share_id):
        raise ImportValidationError(
            "That share link is missing a conversation id.",
            code="invalid_share_url",
        )

    canonical = f"https://claude.ai/share/{share_id}"
    return canonical, share_id


def fetch_share_html(url: str) -> str:
    canonical, _share_id = parse_share_url(url)
    return _fetch_https(canonical, accept_json=False)


def fetch_snapshot_json(share_id: str) -> dict[str, Any]:
    """Fetch the same-host public snapshot JSON if the share HTML is a JS shell."""
    if not _SHARE_ID_RE.fullmatch(share_id):
        raise ImportValidationError(
            "That share link is missing a conversation id.",
            code="invalid_share_url",
        )
    url = f"https://claude.ai/api/chat_snapshots/{share_id}"
    body = _fetch_https(url, accept_json=True)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ImportValidationError(
            "Could not read the conversation from that share page. "
            "Make sure the link is public and copied from Share.",
            code="share_parse_failed",
        ) from exc
    if not isinstance(payload, dict):
        raise ImportValidationError(
            "Could not read the conversation from that share page. "
            "Make sure the link is public and copied from Share.",
            code="share_parse_failed",
        )
    _reject_private_payload(payload)
    return _normalize_share_payload(payload)


def parse_share_html(html: str) -> dict[str, Any]:
    if looks_like_login_wall(html):
        data = _extract_share_payload(html)
        if data is None:
            raise ImportValidationError(
                "That Claude share is private or requires sign-in. "
                "Open the chat, click Share, and paste the public claude.ai/share/... link.",
                code="private_conversation_url",
            )
        _reject_private_payload(data)
        return _normalize_share_payload(data)

    data = _extract_share_payload(html)
    if not isinstance(data, dict):
        raise ImportValidationError(
            "Could not read the conversation from that share page. "
            "Make sure the link is public and copied from Share.",
            code="share_parse_failed",
        )
    _reject_private_payload(data)
    return _normalize_share_payload(data)


def parsed_conversation_from_share(data: dict[str, Any]) -> ParsedConversation:
    parsed = parse_conversation(data)
    if parsed is None:
        raise ImportValidationError(
            "That share link does not contain any messages to import.",
            code="share_parse_failed",
        )
    parsed.messages = [message for message in parsed.messages if (message.content or "").strip()]
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


def looks_like_login_wall(html: str) -> bool:
    lowered = html.lower()
    if "chat_messages" in lowered or "snapshot_name" in lowered:
        return False
    return any(marker in lowered for marker in _LOGIN_MARKERS)


def _fetch_https(url: str, *, accept_json: bool) -> str:
    headers = dict(_BROWSER_HEADERS)
    if accept_json:
        headers["Accept"] = "application/json, text/html;q=0.8"
    request = Request(url, headers=headers, method="GET")
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
                "Claude blocked the share page. Make sure the chat is shared "
                "publicly, then try again.",
                code="private_conversation_url",
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
            "Could not reach Claude to download that share link.",
            code="share_fetch_failed",
        ) from exc


def _reject_private_payload(data: dict[str, Any]) -> None:
    if data.get("is_public") is False:
        raise ImportValidationError(
            "That Claude share is private. Open the chat, click Share, "
            "and paste the public claude.ai/share/... link.",
            code="private_conversation_url",
        )
    error = data.get("error") or data.get("permission_error")
    if error in {"permission_error", "not_allowed", "unauthorized"}:
        raise ImportValidationError(
            "That Claude share is private or requires sign-in.",
            code="private_conversation_url",
        )


def _normalize_share_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    conversation_id = (
        payload.get("conversation_uuid")
        or payload.get("uuid")
        or payload.get("id")
    )
    if isinstance(conversation_id, str) and conversation_id.strip():
        payload["uuid"] = conversation_id.strip()

    title = payload.get("snapshot_name") or payload.get("name") or payload.get("title")
    if isinstance(title, str) and title.strip():
        payload["name"] = title.strip()

    messages = payload.get("chat_messages")
    if not isinstance(messages, list) or not messages:
        linear = payload.get("messages") or payload.get("linear_conversation")
        if isinstance(linear, list):
            payload["chat_messages"] = _messages_from_linear(linear)

    for message in payload.get("chat_messages") or []:
        if not isinstance(message, dict):
            continue
        if not extract_message_text(message):
            message["text"] = ""

    return payload


def _messages_from_linear(linear: list[Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in linear:
        if not isinstance(entry, dict):
            continue
        nested = entry.get("message") if isinstance(entry.get("message"), dict) else entry
        if not isinstance(nested, dict):
            continue
        sender = nested.get("sender") or nested.get("role")
        author = nested.get("author")
        if sender is None and isinstance(author, dict):
            sender = author.get("role")
        content = nested.get("content")
        text = nested.get("text")
        if not text and isinstance(content, dict):
            parts = content.get("parts")
            if isinstance(parts, list):
                text = "\n".join(part for part in parts if isinstance(part, str))
        messages.append(
            {
                "uuid": nested.get("uuid") or nested.get("id") or entry.get("id"),
                "sender": sender,
                "text": text or "",
                "content": content if isinstance(content, list) else nested.get("content"),
                "created_at": nested.get("created_at") or nested.get("create_time"),
                "parent_message_uuid": nested.get("parent_message_uuid") or entry.get("parent"),
                "index": nested.get("index", len(messages)),
            }
        )
    return messages


def _extract_share_payload(html: str) -> dict[str, Any] | None:
    match = _NEXT_DATA_RE.search(html)
    if match:
        found = _payload_from_json_text(match.group(1))
        if found:
            return found

    for match in _JSON_SCRIPT_RE.finditer(html):
        found = _payload_from_json_text(match.group(1))
        if found:
            return found

    for _attrs, body in _SCRIPT_RE.findall(html):
        stripped = body.strip()
        if not stripped:
            continue
        if stripped.startswith("{") or stripped.startswith("["):
            found = _payload_from_json_text(stripped)
            if found:
                return found
        assignment = _json_assignment(stripped)
        if assignment:
            found = _payload_from_json_text(assignment)
            if found:
                return found

    return None


def _json_assignment(script: str) -> str | None:
    for marker in (
        "window.__INITIAL_STATE__ =",
        "window.__remixContext =",
        "window.__NEXT_DATA__ =",
    ):
        index = script.find(marker)
        if index < 0:
            continue
        return script[index + len(marker) :].strip().rstrip(";")
    return None


def _payload_from_json_text(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return _find_claude_payload(parsed)


def _find_claude_payload(obj: Any, depth: int = 0) -> dict[str, Any] | None:
    if depth > 12:
        return None
    if isinstance(obj, dict):
        if isinstance(obj.get("chat_messages"), list):
            return obj
        for key in (
            "snapshot",
            "chatSnapshot",
            "sharedConversation",
            "share",
            "data",
            "pageProps",
            "props",
            "serverResponse",
        ):
            if key in obj:
                found = _find_claude_payload(obj[key], depth + 1)
                if found:
                    return found
        for value in obj.values():
            found = _find_claude_payload(value, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_claude_payload(item, depth + 1)
            if found:
                return found
    return None
