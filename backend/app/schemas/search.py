from datetime import datetime

from pydantic import BaseModel, Field


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


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    conversation_id: str
    retrieved: int = 0
