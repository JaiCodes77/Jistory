from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ask.prompts import (
    NOT_FOUND_ANSWER,
    NOT_FOUND_IN_TAGS,
    SYSTEM_PROMPT,
    build_user_prompt,
    format_context_block,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.llm.base import ChatTurn, LLMProvider
from app.llm.factory import require_llm_provider
from app.llm.gemini import map_gemini_exception
from app.models.ask_session import AskSession, AskTurn
from app.models.conversation import Conversation
from app.retrieval.hybrid import RetrievedChunk, hybrid_retrieve
from app.schemas.conversation import ConversationSummary
from app.schemas.search import (
    AskResponse,
    AskSessionDetail,
    AskSessionListResponse,
    AskSessionSummary,
    AskTurnItem,
    SourceReference,
)
from app.user_settings.store import resolve_settings

logger = logging.getLogger("jistory.ask")

MAX_SNIPPET = 280
MAX_TAGGED_CONVERSATIONS = 8
SESSION_TITLE_MAX = 80


@dataclass
class _AskPrep:
    question: str
    settings: Settings
    tagged: list[Conversation]
    tagged_ids: list[str]
    tagged_titles: list[str]
    session: AskSession
    history: list[AskTurn]
    chunks: list[RetrievedChunk]
    sources: list[SourceReference]


def ask(
    db: Session,
    settings: Settings,
    *,
    message: str,
    conversation_id: str | None,
    tagged_conversation_ids: list[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    llm: LLMProvider | None = None,
) -> AskResponse:
    prep = _prepare_ask(
        db,
        settings,
        message=message,
        conversation_id=conversation_id,
        tagged_conversation_ids=tagged_conversation_ids,
        date_from=date_from,
        date_to=date_to,
    )
    if not prep.chunks:
        answer = _empty_retrieval_answer(db, prep.tagged)
        _persist_turn(db, prep.session, prep.question, answer, prep.sources, prep.tagged_ids)
        return AskResponse(
            answer=answer,
            sources=[],
            conversation_id=prep.session.id,
            retrieved=0,
        )

    prompt = build_user_prompt(
        prep.question,
        [_context_block(i, chunk) for i, chunk in enumerate(prep.chunks, start=1)],
        tagged_titles=prep.tagged_titles or None,
    )
    provider = llm or require_llm_provider(prep.settings)
    chat_history = [ChatTurn(role=turn.role, content=turn.content) for turn in prep.history]

    try:
        answer = provider.generate(system=SYSTEM_PROMPT, prompt=prompt, history=chat_history)
    except AppError:
        raise
    except Exception:
        logger.exception("LLM generation failed")
        raise AppError(
            "Jistory could not generate an answer. Please try again.",
            code="llm_unavailable",
            status_code=502,
        )

    if not (answer or "").strip():
        answer = NOT_FOUND_ANSWER

    _persist_turn(db, prep.session, prep.question, answer, prep.sources, prep.tagged_ids)
    return AskResponse(
        answer=answer,
        sources=prep.sources,
        conversation_id=prep.session.id,
        retrieved=len(prep.chunks),
    )


def ask_stream(
    db: Session,
    settings: Settings,
    *,
    message: str,
    conversation_id: str | None,
    tagged_conversation_ids: list[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    llm: LLMProvider | None = None,
) -> Iterator[dict[str, Any]]:
    prep = _prepare_ask(
        db,
        settings,
        message=message,
        conversation_id=conversation_id,
        tagged_conversation_ids=tagged_conversation_ids,
        date_from=date_from,
        date_to=date_to,
    )
    yield {
        "type": "sources",
        "sources": [source.model_dump(mode="json") for source in prep.sources],
        "retrieved": len(prep.chunks),
        "conversation_id": prep.session.id,
    }

    if not prep.chunks:
        answer = _empty_retrieval_answer(db, prep.tagged)
        if answer:
            yield {"type": "token", "text": answer}
        _persist_turn(db, prep.session, prep.question, answer, prep.sources, prep.tagged_ids)
        yield {
            "type": "done",
            "conversation_id": prep.session.id,
            "retrieved": 0,
            "answer": answer,
        }
        return

    prompt = build_user_prompt(
        prep.question,
        [_context_block(i, chunk) for i, chunk in enumerate(prep.chunks, start=1)],
        tagged_titles=prep.tagged_titles or None,
    )
    try:
        provider = llm or require_llm_provider(prep.settings)
    except AppError as exc:
        yield {"type": "error", "error": exc.message, "code": exc.code}
        return

    chat_history = [ChatTurn(role=turn.role, content=turn.content) for turn in prep.history]
    parts: list[str] = []
    try:
        for token in provider.generate_stream(
            system=SYSTEM_PROMPT, prompt=prompt, history=chat_history
        ):
            if not token:
                continue
            parts.append(token)
            yield {"type": "token", "text": token}
        answer = "".join(parts).strip() or NOT_FOUND_ANSWER
    except AppError as exc:
        yield {"type": "error", "error": exc.message, "code": exc.code}
        return
    except Exception as exc:
        mapped = map_gemini_exception(exc)
        logger.exception("LLM stream failed")
        yield {"type": "error", "error": mapped.message, "code": mapped.code}
        return

    _persist_turn(db, prep.session, prep.question, answer, prep.sources, prep.tagged_ids)
    yield {
        "type": "done",
        "conversation_id": prep.session.id,
        "retrieved": len(prep.chunks),
        "answer": answer,
    }


def _prepare_ask(
    db: Session,
    settings: Settings,
    *,
    message: str,
    conversation_id: str | None,
    tagged_conversation_ids: list[str] | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> _AskPrep:
    question = message.strip()
    if not question:
        raise AppError("Enter a question.", code="empty_message", status_code=400)

    settings = resolve_settings(settings)
    tagged = _resolve_tagged_conversations(db, tagged_conversation_ids)
    tagged_ids = [row.id for row in tagged]
    tagged_titles = [
        row.title.strip() if row.title and row.title.strip() else "Untitled conversation"
        for row in tagged
    ]
    session = _get_or_create_session(db, conversation_id, tagged_ids)
    history = list(session.turns)[-settings.ask_max_history_turns :]
    retrieval_query = _retrieval_query(question, history)
    chunks = hybrid_retrieve(
        db,
        retrieval_query,
        settings,
        limit=settings.retrieval_limit,
        conversation_ids=tagged_ids or None,
        date_from=date_from,
        date_to=date_to,
    )
    return _AskPrep(
        question=question,
        settings=settings,
        tagged=tagged,
        tagged_ids=tagged_ids,
        tagged_titles=tagged_titles,
        session=session,
        history=history,
        chunks=chunks,
        sources=[_to_source(chunk) for chunk in chunks],
    )


def _empty_retrieval_answer(db: Session, tagged: list[Conversation]) -> str:
    if tagged:
        return NOT_FOUND_IN_TAGS
    if not conversation_exists(db):
        return "Jistory doesn't have any memories yet. Import a conversation history first."
    return NOT_FOUND_ANSWER


def _resolve_tagged_conversations(db: Session, raw_ids: list[str] | None) -> list[Conversation]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in raw_ids or []:
        value = (raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    if not unique:
        return []
    if len(unique) > MAX_TAGGED_CONVERSATIONS:
        raise AppError(
            "You can tag at most 8 conversations.",
            code="too_many_tags",
            status_code=400,
        )
    rows = list(db.scalars(select(Conversation).where(Conversation.id.in_(unique))).all())
    found = {row.id: row for row in rows}
    missing = [conversation_id for conversation_id in unique if conversation_id not in found]
    if missing:
        raise AppError(
            "A tagged conversation was not found.",
            code="tagged_not_found",
            status_code=400,
        )
    return [found[conversation_id] for conversation_id in unique]


def _get_or_create_session(
    db: Session,
    conversation_id: str | None,
    tagged_ids: list[str] | None = None,
) -> AskSession:
    if conversation_id:
        session = db.scalar(
            select(AskSession)
            .where(AskSession.id == conversation_id)
            .options(selectinload(AskSession.turns))
        )
        if session is None:
            raise AppError("Ask conversation was not found.", code="not_found", status_code=404)
        _store_session_tags(session, tagged_ids)
        return session

    session = AskSession()
    _store_session_tags(session, tagged_ids)
    db.add(session)
    db.flush()
    session.turns = []
    return session


def _retrieval_query(question: str, history: list[AskTurn]) -> str:
    words = question.split()
    if len(words) >= 8 or not history:
        return question
    prior = [turn.content for turn in history if turn.role == "user"][-2:]
    last_assistant = next(
        (turn.content for turn in reversed(history) if turn.role == "assistant"),
        "",
    )
    assistant_hint = " ".join(last_assistant.split()[:40]).strip()
    parts = [*prior]
    if assistant_hint:
        parts.append(assistant_hint)
    parts.append(question)
    return " ".join(part for part in parts if part)


def _context_block(index: int, chunk: RetrievedChunk) -> str:
    ts = _format_ts(chunk.timestamp)
    return format_context_block(
        index,
        title=chunk.conversation_title,
        source=chunk.source,
        timestamp=ts,
        text=chunk.text or chunk.snippet,
    )


def _to_source(chunk: RetrievedChunk) -> SourceReference:
    snippet = (chunk.snippet or chunk.text or "").replace("\n", " ").strip()
    if len(snippet) > MAX_SNIPPET:
        snippet = snippet[: MAX_SNIPPET - 1] + "…"
    return SourceReference(
        conversation_id=chunk.conversation_id,
        message_id=chunk.message_id or None,
        title=chunk.conversation_title,
        source=chunk.source,
        timestamp=chunk.timestamp,
        snippet=snippet,
    )


def _persist_turn(
    db: Session,
    session: AskSession,
    question: str,
    answer: str,
    sources: list[SourceReference],
    tagged_ids: list[str] | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    if not (session.title or "").strip():
        session.title = _session_title(question)
    _store_session_tags(session, tagged_ids)
    db.add(AskTurn(session_id=session.id, role="user", content=question, created_at=now))
    db.add(
        AskTurn(
            session_id=session.id,
            role="assistant",
            content=answer,
            sources_json=json.dumps([s.model_dump(mode="json") for s in sources]),
            created_at=now,
        )
    )
    session.updated_at = now
    db.add(session)
    db.commit()


def _format_ts(value: datetime | None) -> str:
    if value is None:
        return "unknown date"
    return value.strftime("%b %d, %Y")


def conversation_exists(db: Session) -> bool:
    return db.scalar(select(Conversation.id).limit(1)) is not None


def list_ask_sessions(db: Session, *, limit: int = 50) -> AskSessionListResponse:
    rows = list(
        db.scalars(
            select(AskSession).order_by(AskSession.updated_at.desc()).limit(limit)
        ).all()
    )
    return AskSessionListResponse(items=[_session_summary(row) for row in rows])


def get_ask_session(db: Session, session_id: str) -> AskSessionDetail:
    session = db.scalar(
        select(AskSession)
        .where(AskSession.id == session_id)
        .options(selectinload(AskSession.turns))
    )
    if session is None:
        raise AppError("Ask conversation was not found.", code="not_found", status_code=404)
    tagged_ids = _load_session_tag_ids(session)
    tagged_rows = _resolve_existing_conversations(db, tagged_ids)
    turns = [
        AskTurnItem(
            id=turn.id,
            role=turn.role,
            content=turn.content,
            sources=_parse_sources(turn.sources_json),
            created_at=turn.created_at,
        )
        for turn in session.turns
    ]
    summary = _session_summary(session)
    return AskSessionDetail(
        **summary.model_dump(),
        turns=turns,
        tagged_conversations=[ConversationSummary.model_validate(row) for row in tagged_rows],
    )


def delete_ask_session(db: Session, session_id: str) -> str:
    session = db.get(AskSession, session_id)
    if session is None:
        raise AppError("Ask conversation was not found.", code="not_found", status_code=404)
    deleted_id = session.id
    db.delete(session)
    db.commit()
    return deleted_id


def _session_summary(session: AskSession) -> AskSessionSummary:
    return AskSessionSummary(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        tagged_conversation_ids=_load_session_tag_ids(session),
    )


def _session_title(question: str) -> str:
    one_line = " ".join(question.split())
    if len(one_line) <= SESSION_TITLE_MAX:
        return one_line
    return one_line[: SESSION_TITLE_MAX - 1] + "…"


def _store_session_tags(session: AskSession, tagged_ids: list[str] | None) -> None:
    if tagged_ids is None:
        return
    session.tagged_conversation_ids = json.dumps(tagged_ids)


def _load_session_tag_ids(session: AskSession) -> list[str]:
    raw = session.tagged_conversation_ids
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    unique: list[str] = []
    seen: set[str] = set()
    for item in data:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _resolve_existing_conversations(db: Session, conversation_ids: list[str]) -> list[Conversation]:
    if not conversation_ids:
        return []
    rows = list(db.scalars(select(Conversation).where(Conversation.id.in_(conversation_ids))).all())
    found = {row.id: row for row in rows}
    return [found[conversation_id] for conversation_id in conversation_ids if conversation_id in found]


def _parse_sources(raw: str | None) -> list[SourceReference]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    sources: list[SourceReference] = []
    for item in data:
        try:
            sources.append(SourceReference.model_validate(item))
        except ValidationError:
            continue
    return sources
