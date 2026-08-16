from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    importId: str
    source: str
    folder: str
    status: str
    filename: str | None = None
    fileSize: int = 0
    importedAt: datetime | None = None
    notes: str | None = None
    conversations: int | None = None
    messages: int | None = None
    skipped: int | None = None
    chunks_indexed: int | None = None
    index_error: str | None = None
    embedding_status: str | None = None
    embedding_status_detail: str | None = None


class ImportErrorResponse(BaseModel):
    success: bool = False
    error: str
    code: str
