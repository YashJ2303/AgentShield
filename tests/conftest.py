import pytest
import os
import sys
import threading
from fastapi.testclient import TestClient

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Dedicated throwaway test database file (never touches agentshield.db)
TEST_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_throwaway.db"))
TEST_DB_URL = f"sqlite:///{TEST_DB_PATH.replace(os.sep, '/')}"

os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["ENV"] = "test"
os.environ["ADMIN_TOKEN"] = "test-admin-secret"

from server.app.config import settings
settings.DATABASE_URL = TEST_DB_URL
settings.ENV = "test"
settings.ADMIN_TOKEN = "test-admin-secret"

import server.app.database as db_mod
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

connect_args = {"check_same_thread": False, "timeout": 30.0}
db_mod.engine = create_engine(TEST_DB_URL, connect_args=connect_args, pool_pre_ping=True)
db_mod.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_mod.engine)

engine = db_mod.engine
TestingSessionLocal = db_mod.SessionLocal

from server.app.database import Base, get_db
from server.app.main import app
from server.app.models.api_key import ApiKey
from server.app.services.auth import hash_api_key

TEST_API_KEY = "test-agent-key-secret-123"
TEST_API_KEY_HASH = hash_api_key(TEST_API_KEY)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass
    Base.metadata.create_all(bind=engine)

    # Seed test API key in throwaway db if not existing
    with TestingSessionLocal() as s:
        existing = s.query(ApiKey).filter(ApiKey.key_hash == TEST_API_KEY_HASH).first()
        if not existing:
            key = ApiKey(
                key_hash=TEST_API_KEY_HASH,
                label="test-agent-suite",
                is_active=True,
            )
            s.add(key)
            s.commit()

    yield

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


@pytest.fixture
def db_session():
    with TestingSessionLocal() as session:
        yield session


_test_db_lock = threading.Lock()


@pytest.fixture
def client(db_session):
    def override_get_db():
        with _test_db_lock:
            yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
