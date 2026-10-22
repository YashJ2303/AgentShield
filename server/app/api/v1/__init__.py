from fastapi import APIRouter
from server.app.api.v1.health import router as health_router
from server.app.api.v1.ingest import router as ingest_router
from server.app.api.v1.runs import router as runs_router
from server.app.api.v1.gateway import router as gateway_router
from server.app.api.v1.policies import router as policies_router
from server.app.api.v1.approvals import router as approvals_router
from server.app.api.v1.analytics import router as analytics_router
from server.app.api.v1.alerts import router as alerts_router
from server.app.api.v1.replay import router as replay_router, replays_router
from server.app.api.v1.sessions import router as sessions_router
from server.app.api.v1.eval_results import router as eval_results_router
from server.app.api.v1.live_agent import router as live_agent_router

v1_router = APIRouter()
v1_router.include_router(health_router)
v1_router.include_router(ingest_router)
v1_router.include_router(runs_router)
v1_router.include_router(sessions_router)
v1_router.include_router(gateway_router)
v1_router.include_router(policies_router)
v1_router.include_router(approvals_router)
v1_router.include_router(analytics_router)
v1_router.include_router(alerts_router)
v1_router.include_router(replay_router)
v1_router.include_router(replays_router)
v1_router.include_router(eval_results_router)
v1_router.include_router(live_agent_router)

__all__ = ["v1_router"]

