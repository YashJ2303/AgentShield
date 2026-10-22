from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from server.app.database import get_db
from server.app.models.session import SessionModel
from server.app.models.run import Run
from server.app.schemas.session import SessionResponse, SessionListResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List agent sessions with run counts.
    """
    total = db.query(SessionModel).count()
    sessions = (
        db.query(SessionModel)
        .order_by(desc(SessionModel.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for s in sessions:
        count = db.query(Run).filter(Run.session_id == s.id).count()
        results.append(
            SessionResponse(
                id=s.id,
                session_id=s.session_id,
                name=s.name,
                session_metadata=s.session_metadata or {},
                run_count=count,
                created_at=s.created_at,
            )
        )

    return SessionListResponse(total=total, sessions=results)
