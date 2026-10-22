"""Database Reset Script for AgentShield.

Resets agentshield.db to a clean initial state containing only:
- Base database schema
- Default API key (in dev/test environment)
- Version 1 baseline security policy (active)

Usage:
    python scripts/reset_demo_db.py
"""

import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from server.app.database import engine, Base, SessionLocal
from server.app.config import settings
from server.app.main import _seed_initial_data


def reset_database():
    db_file = os.path.abspath(os.path.join(ROOT_DIR, "agentshield.db"))
    print(f"[Reset DB] Resetting AgentShield SQLite database: {db_file}")

    # Remove database file and journal/wal files if they exist
    for ext in ["", "-shm", "-wal", "-journal"]:
        path = f"{db_file}{ext}"
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"[Reset DB] Removed {path}")
            except Exception as e:
                print(f"[Reset DB] Warning removing {path}: {e}")

    # Ensure tables are created fresh
    Base.metadata.create_all(bind=engine)
    print("[Reset DB] Created fresh database tables.")

    # Seed development API key and active default policy
    _seed_initial_data()
    print("[Reset DB] Seeded initial API key and active baseline policy.")
    print("[Reset DB] Database is clean and ready for demo population.")


if __name__ == "__main__":
    reset_database()
