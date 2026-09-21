#!/usr/bin/env python3
"""Initialize database and seed demo data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import SessionLocal, init_db
from app.services.seed import seed_database

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        seed_database(db)
        print("Database initialized and seeded.")
    finally:
        db.close()
