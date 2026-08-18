from datetime import datetime

from pydantic import BaseModel, Field


class SourceCount(BaseModel):
    name: str
    count: int


class TimeBucket(BaseModel):
    date: str
    count: int


class RecentConversation(BaseModel):
    id: str
    title: str | None
    source: str
    updated_at: datetime | None
    message_count: int


class LatestImport(BaseModel):
    id: str
    source: str
    filename: str | None
    imported_at: datetime | None
    status: str
    conversations: int | None = None


class TopicCount(BaseModel):
    term: str
    count: int


class DashboardResponse(BaseModel):
    total_conversations: int
    total_messages: int
    sources: list[SourceCount]
    latest_import: LatestImport | None
    conversations_over_time: list[TimeBucket]
    recent_conversations: list[RecentConversation]
    frequent_topics: list[TopicCount]


class UserSettingsPublic(BaseModel):
    llm_provider: str
    gemini_model: str
    api_key_configured: bool
    embedding_provider: str
    embedding_model: str
    retrieval_limit: int
    stored_locally: bool = True
    sent_to_gemini_on_ask: bool = True
    embedding_status: str = "idle"
    embedding_status_detail: str = ""
    cursor_import_path: str = ""


class UserSettingsUpdate(BaseModel):
    gemini_model: str | None = Field(default=None, max_length=128)
    gemini_api_key: str | None = Field(default=None, max_length=512)
    retrieval_limit: int | None = Field(default=None, ge=1, le=32)
    embedding_provider: str | None = None
    cursor_import_path: str | None = Field(default=None, max_length=2048)
