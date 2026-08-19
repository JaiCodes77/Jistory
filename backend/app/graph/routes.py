from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.graph.service import get_graph, rebuild_graph
from app.schemas.graph import GraphRebuildResponse, GraphResponse
from app.schemas.import_job import ImportErrorResponse

router = APIRouter(prefix="/graph", tags=["graph"])


def _error(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ImportErrorResponse(error=exc.message, code=exc.code).model_dump(),
    )


def _parse_optional_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


@router.get("", response_model=GraphResponse)
def read_graph(
    source: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    min_weight: float = Query(0.0, ge=0.0, le=1.0),
    include_isolated: bool = Query(True),
    db: Session = Depends(get_db),
) -> GraphResponse | JSONResponse:
    try:
        parsed_from = _parse_optional_dt(date_from)
        parsed_to = _parse_optional_dt(date_to)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content=ImportErrorResponse(
                error="Invalid date range. Use ISO-8601 timestamps.",
                code="invalid_date",
            ).model_dump(),
        )

    try:
        return get_graph(
            db,
            source=source,
            date_from=parsed_from,
            date_to=parsed_to,
            min_weight=min_weight,
            include_isolated=include_isolated,
        )
    except AppError as exc:
        return _error(exc)


@router.post("/rebuild", response_model=GraphRebuildResponse)
def post_rebuild(db: Session = Depends(get_db)) -> GraphRebuildResponse:
    return rebuild_graph(db)
