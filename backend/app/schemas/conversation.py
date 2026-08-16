from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    source: str
    created_at: datetime | None
    updated_at: datetime | None
    message_count: int
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None


class ConversationListResponse(BaseModel):
    items: list[ConversationSummary]
    page: int
    page_size: int
    total: int


class MessageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    created_at: datetime | None
    sequence_number: int
    parent_message_id: str | None = None


class ConversationDetail(ConversationSummary):
    pass


class MessageListResponse(BaseModel):
    items: list[MessageItem]
    page: int
    page_size: int
    total: int
    conversation: ConversationDetail


class ConversationListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)
    search: str | None = None
    source: str | None = None
    range: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    sort: str = "newest"
