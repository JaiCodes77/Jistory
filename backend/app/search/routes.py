from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.retrieval.hybrid import hybrid_retrieve, search_fts
from app.schemas.import_job import ImportErrorResponse
from app.schemas.search import SearchHit, SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=500),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    mode: str = Query("hybrid"),
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

    offset = (page - 1) * page_size
    if mode == "keyword":
        hits, total = search_fts(db, query, limit=page_size, offset=offset)
    else:
        fused = hybrid_retrieve(db, query, settings, limit=page_size * page)
        total = len(fused)
        hits = fused[offset : offset + page_size]
        if mode == "hybrid" and not hits:
            hits, total = search_fts(db, query, limit=page_size, offset=offset)

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
