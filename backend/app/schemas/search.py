from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.conversation import ConversationSummary


class SearchHit(BaseModel):
    conversation_id: str
    message_id: str
    conversation_title: str | None
    snippet: str
    source: str
    timestamp: datetime | None
    score: float = 0.0
    match_type: str = "keyword"


class SearchResponse(BaseModel):
    results: list[SearchHit]
    page: int
    page_size: int
    total: int
    query: str


class SourceReference(BaseModel):
    conversation_id: str
    message_id: str | None = None
    title: str | None
    source: str
    timestamp: datetime | None = None
    snippet: str = ""


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    tagged_conversation_ids: list[str] = Field(default_factory=list, max_length=8)
    date_from: datetime | None = None
    date_to: datetime | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    conversation_id: str
    retrieved: int = 0


class AskTurnItem(BaseModel):
    id: str
    role: str
    content: str
    sources: list[SourceReference] = Field(default_factory=list)
    created_at: datetime | None = None


class AskSessionSummary(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    tagged_conversation_ids: list[str] = Field(default_factory=list)


class AskSessionListResponse(BaseModel):
    items: list[AskSessionSummary]


class AskSessionDetail(AskSessionSummary):
    turns: list[AskTurnItem] = Field(default_factory=list)
    tagged_conversations: list[ConversationSummary] = Field(default_factory=list)


class AskSessionDeleteResponse(BaseModel):
    success: bool = True
    id: str
