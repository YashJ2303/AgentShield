from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from server.app.config import settings
from server.app.logging import setup_logging
from server.app.database import engine, Base
import server.app.models  # ensure all models registered
from server.app.api.v1 import v1_router

setup_logging(debug=settings.DEBUG)


def _seed_initial_data():
    from server.app.database import SessionLocal
    from server.app.models.policy import PolicyVersion
    from server.app.services.auth import seed_default_api_key
    import os

    env = (getattr(settings, "ENV", None) or "production").lower()
    example_tokens = {
        "agentshield-admin-supersecret-token-2026",
        "agentshield-dev-key-12345",
    }

    # In non-dev environments, strictly refuse to start if using example credentials
    if env not in ("dev", "test"):
        if settings.ADMIN_TOKEN in example_tokens:
            raise RuntimeError(
                f"Security violation: Server startup aborted. Non-dev environment (ENV='{settings.ENV}') "
                f"cannot use insecure example ADMIN_TOKEN."
            )
        # Do not seed development credentials in non-dev environments
        return

    db = SessionLocal()
    try:
        # 1. Seed default API key in dev/test environment
        seed_default_api_key(db)

        # 2. Seed baseline policy if table is empty or ensure an active policy exists
        policy_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../policies/default_policy.yaml"))
        active_count = db.query(PolicyVersion).filter(PolicyVersion.is_active == True).count()
        if active_count == 0:
            latest = db.query(PolicyVersion).order_by(PolicyVersion.version_number.desc()).first()
            if latest:
                latest.is_active = True
                db.commit()
            elif os.path.exists(policy_path):
                with open(policy_path, "r", encoding="utf-8") as f:
                    content = f.read()
                record = PolicyVersion(
                    version_number=1,
                    yaml_content=content,
                    change_note="Initial baseline policy auto-seeded on server startup",
                    is_active=True,
                    created_by="system",
                )
                db.add(record)
                db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    _seed_initial_data()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AgentShield: A Production Safety, Observability & Policy Gateway for AI Agents",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "docs": "/docs",
    }
