import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from server.app.database import SessionLocal
from server.app.models.approval import Approval
from server.app.models.run import Run
from server.app.services.approval_manager import compute_call_hash

db = SessionLocal()
now = datetime.now(timezone.utc)

# 1. Pending approval with active 60s countdown
run_1 = str(uuid.uuid4())
args_1 = {
    "target_table": "customer_pii_vault",
    "batch_size": 50000,
    "destination": "s3://secure-cold-storage/export_2026.parquet",
    "requested_scope": "FULL_EXPORT"
}
app_1 = Approval(
    id=str(uuid.uuid4()),
    run_id=run_1,
    tool_name="bulk_pii_export",
    tool_args=args_1,
    call_hash=compute_call_hash(run_1, "bulk_pii_export", args_1),
    status="pending",
    timeout_seconds=90,
    requested_at=now - timedelta(seconds=15),
    is_consumed=0
)
db.add(app_1)

# 2. Approved approval
run_2 = str(uuid.uuid4())
args_2 = {
    "account": "AC-GLOBAL-TREASURY-01",
    "amount": 175000.0,
    "recipient": "AWS Enterprise Cloud Services",
    "memo": "Annual reserved instance capacity renewal"
}
app_2 = Approval(
    id=str(uuid.uuid4()),
    run_id=run_2,
    tool_name="wire_transfer",
    tool_args=args_2,
    call_hash=compute_call_hash(run_2, "wire_transfer", args_2),
    status="approved",
    timeout_seconds=60,
    requested_at=now - timedelta(minutes=10),
    decided_at=now - timedelta(minutes=9),
    decision_reason="Approved per Q4 infrastructure budget allocation",
    decided_by="cfo_office",
    is_consumed=1
)
db.add(app_2)

# 3. Rejected approval
run_3 = str(uuid.uuid4())
args_3 = {
    "command": "rm -rf /var/log/audit/ && service auditd stop",
    "host": "prod-db-primary-01"
}
app_3 = Approval(
    id=str(uuid.uuid4()),
    run_id=run_3,
    tool_name="privileged_shell_exec",
    tool_args=args_3,
    call_hash=compute_call_hash(run_3, "privileged_shell_exec", args_3),
    status="rejected",
    timeout_seconds=60,
    requested_at=now - timedelta(hours=1),
    decided_at=now - timedelta(minutes=58),
    decision_reason="Destructive audit log suppression attempt blocked by SOC lead",
    decided_by="soc_analyst_2",
    is_consumed=0
)
db.add(app_3)

# 4. Timed out approval
run_4 = str(uuid.uuid4())
args_4 = {
    "dataset": "credit_card_fraud_training",
    "export_format": "csv"
}
app_4 = Approval(
    id=str(uuid.uuid4()),
    run_id=run_4,
    tool_name="dataset_export",
    tool_args=args_4,
    call_hash=compute_call_hash(run_4, "dataset_export", args_4),
    status="timed_out",
    timeout_seconds=30,
    requested_at=now - timedelta(hours=3),
    decided_at=now - timedelta(hours=2, minutes=59, seconds=30),
    decision_reason="Approval request timed out before operator response",
    is_consumed=0
)
db.add(app_4)

db.commit()
db.close()
print("Approvals seeded successfully!")
