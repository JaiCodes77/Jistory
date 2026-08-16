from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dashboard.service import get_dashboard
from app.db.session import get_db
from app.schemas.dashboard import DashboardResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db)) -> DashboardResponse:
    return get_dashboard(db)
