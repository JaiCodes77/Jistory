from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.retrieval.hybrid import HYBRID_SEARCH_CANDIDATES, hybrid_retrieve, search_fts
from app.schemas.import_job import ImportErrorResponse
from app.schemas.search import SearchHit, SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


def _parse_optional_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=500),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    mode: str = Query("hybrid"),
    source: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SearchResponse | JSONResponse:
    query = q.strip()
    if not query:
        return JSONResponse(
            status_code=400,
            content=ImportErrorResponse(
                error="Enter a search query.",
                code="empty_query",
            ).model_dump(),
        )

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

    offset = (page - 1) * page_size
    if mode == "keyword":
        hits, total = search_fts(
            db,
            query,
            limit=page_size,
            offset=offset,
            date_from=parsed_from,
            date_to=parsed_to,
            source=source,
        )
    else:
        fused = hybrid_retrieve(
            db,
            query,
            settings,
            limit=HYBRID_SEARCH_CANDIDATES,
            date_from=parsed_from,
            date_to=parsed_to,
            source=source,
        )
        if not fused:
            hits, total = search_fts(
                db,
                query,
                limit=page_size,
                offset=offset,
                date_from=parsed_from,
                date_to=parsed_to,
                source=source,
            )
        else:
            total = len(fused)
            hits = fused[offset : offset + page_size]

    return SearchResponse(
        results=[
            SearchHit(
                conversation_id=hit.conversation_id,
                message_id=hit.message_id,
                conversation_title=hit.conversation_title,
                snippet=hit.snippet,
                source=hit.source,
                timestamp=hit.timestamp,
                score=hit.score,
                match_type=hit.match_type,
            )
            for hit in hits
        ],
        page=page,
        page_size=page_size,
        total=total,
        query=query,
    )
