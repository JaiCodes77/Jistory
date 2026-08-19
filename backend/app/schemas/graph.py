from datetime import datetime

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    title: str | None
    source: str
    message_count: int
    created_at: datetime | None = None
    last_message_at: datetime | None = None
    snippet: str = ""
    degree: int = 0
    topics: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    weight: float
    reason: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    built_at: datetime | None = None
    truncated: bool = False
    isolated: int = 0


class GraphRebuildResponse(BaseModel):
    nodes: int
    edges: int
    built_at: datetime | None = None


class RelatedConversation(BaseModel):
    id: str
    title: str | None
    source: str
    message_count: int
    last_message_at: datetime | None = None
    snippet: str = ""
    weight: float
    reason: str


class RelatedResponse(BaseModel):
    items: list[RelatedConversation] = Field(default_factory=list)
