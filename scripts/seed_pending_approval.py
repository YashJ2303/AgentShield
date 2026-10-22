import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from server.app.database import SessionLocal
from server.app.models.approval import Approval
from server.app.services.approval_manager import compute_call_hash

db = SessionLocal()
now = datetime.now(timezone.utc)
run_id = str(uuid.uuid4())
args = {
    "account": "AC-GLOBAL-TREASURY-02",
    "amount": 750000.0,
    "destination_country": "CH",
    "notes": "Emergency multi-cloud failover infrastructure capacity allocation"
}
app = Approval(
    id=str(uuid.uuid4()),
    run_id=run_id,
    tool_name="high_value_wire_transfer",
    tool_args=args,
    call_hash=compute_call_hash(run_id, "high_value_wire_transfer", args),
    status="pending",
    timeout_seconds=300,
    requested_at=now - timedelta(seconds=5),
    is_consumed=0
)
db.add(app)
db.commit()
db.close()
print(f"Created pending approval: {app.id}")
