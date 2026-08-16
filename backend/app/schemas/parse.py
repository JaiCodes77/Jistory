from pydantic import BaseModel


class ParseJobResponse(BaseModel):
    success: bool = True
    importId: str
    conversations: int
    messages: int
    skipped: int
    elapsed: str
    elapsed_ms: int = 0
    status: str = "completed"
