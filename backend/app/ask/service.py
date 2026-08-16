from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ask.prompts import NOT_FOUND_ANSWER, SYSTEM_PROMPT, build_user_prompt, format_context_block
from app.core.config import Settings
from app.core.errors import AppError
from app.llm.base import ChatTurn, LLMProvider
from app.llm.factory import require_llm_provider
from app.models.ask_session import AskSession, AskTurn
from app.models.conversation import Conversation
from app.retrieval.hybrid import RetrievedChunk, hybrid_retrieve
from app.schemas.search import AskResponse, SourceReference
from app.user_settings.store import resolve_settings

logger = logging.getLogger("jistory.ask")

MAX_SNIPPET = 280


def ask(
    db: Session,
    settings: Settings,
    *,
    message: str,
    conversation_id: str | None,
    llm: LLMProvider | None = None,
) -> AskResponse:
    question = message.strip()
    if not question:
        raise AppError("Enter a question.", code="empty_message", status_code=400)

    settings = resolve_settings(settings)
    session = _get_or_create_session(db, conversation_id)
    history = list(session.turns)[-settings.ask_max_history_turns :]

    retrieval_query = _retrieval_query(question, history)
    chunks = hybrid_retrieve(db, retrieval_query, settings, limit=settings.retrieval_limit)

    sources = [_to_source(chunk) for chunk in chunks]
    if not chunks:
        answer = (
            "Jistory doesn't have any memories yet. Import a conversation history first."
            if not conversation_exists(db)
            else NOT_FOUND_ANSWER
        )
        _persist_turn(db, session, question, answer, sources)
        return AskResponse(
            answer=answer,
            sources=[],
            conversation_id=session.id,
            retrieved=0,
        )

    prompt = build_user_prompt(question, [_context_block(i, chunk) for i, chunk in enumerate(chunks, start=1)])
    provider = llm or require_llm_provider(settings)
    chat_history = [ChatTurn(role=turn.role, content=turn.content) for turn in history]

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

    _persist_turn(db, session, question, answer, sources)
    return AskResponse(
        answer=answer,
        sources=sources,
        conversation_id=session.id,
        retrieved=len(chunks),
    )


def _get_or_create_session(db: Session, conversation_id: str | None) -> AskSession:
    if conversation_id:
        session = db.scalar(
            select(AskSession)
            .where(AskSession.id == conversation_id)
            .options(selectinload(AskSession.turns))
        )
        if session is None:
            raise AppError("Ask conversation was not found.", code="not_found", status_code=404)
        return session

    session = AskSession()
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
) -> None:
    now = datetime.now(timezone.utc)
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
