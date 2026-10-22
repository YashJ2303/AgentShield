import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from server.app.models.rate_limit import RateLimitCounter


def get_rate_limit_counts_for_run(db: Session, run_id: str) -> dict[str, int]:
    """Retrieve all current tool call counts for a given run from DB."""
    records = db.query(RateLimitCounter).filter(RateLimitCounter.run_id == run_id).all()
    return {r.tool_name: r.call_count for r in records}


def increment_rate_limit_counter(db: Session, run_id: str, tool_name: str) -> int:
    """
    Atomically increment tool execution count in DB.
    Guarantees consistent counters under concurrent executions.
    """
    now = datetime.now(timezone.utc)

    # In SQLite, table-level lock applies; in PostgreSQL with_for_update locks row
    is_sqlite = db.bind.dialect.name == "sqlite" if db.bind else True
    q = db.query(RateLimitCounter).filter(
        RateLimitCounter.run_id == run_id,
        RateLimitCounter.tool_name == tool_name,
    )
    if not is_sqlite:
        q = q.with_for_update()

    record = q.first()

    if not record:
        try:
            record = RateLimitCounter(
                id=str(uuid.uuid4()),
                run_id=run_id,
                tool_name=tool_name,
                call_count=1,
                updated_at=now,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.call_count
        except Exception:
            db.rollback()
            record = db.query(RateLimitCounter).filter(
                RateLimitCounter.run_id == run_id,
                RateLimitCounter.tool_name == tool_name,
            ).first()

    if record:
        db.query(RateLimitCounter).filter(
            RateLimitCounter.id == record.id
        ).update(
            {"call_count": RateLimitCounter.call_count + 1, "updated_at": now}
        )
        db.commit()
        db.refresh(record)
        return record.call_count

    return 1
