from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.ask.service import ask
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.import_job import ImportErrorResponse
from app.schemas.search import AskRequest, AskResponse

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
def ask_jistory(
    payload: AskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AskResponse | JSONResponse:
    try:
        return ask(
            db,
            settings,
            message=payload.message,
            conversation_id=payload.conversation_id,
        )
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
        )
