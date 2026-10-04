"""
Database engine configuration, session management, and auto-seeding.
"""

import os
import sys
import json
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from Database.models import Base, SchemeModel, UserProfileModel

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "Database"
DB_PATH = DB_DIR / "assistant.db"
SCHEMES_JSON_PATH = BASE_DIR / "Documents" / "schemes_knowledge_base.json"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Yields a database session context."""
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def seed_schemes_if_needed(db: Session) -> int:
    """Seeds scheme records from schemes_knowledge_base.json if table is empty."""
    count = db.query(SchemeModel).count()
    if count > 0:
        return count

    if not SCHEMES_JSON_PATH.exists():
        logger.warning(f"Schemes JSON not found at {SCHEMES_JSON_PATH}")
        return 0

    with open(SCHEMES_JSON_PATH, "r", encoding="utf-8") as f:
        schemes_data = json.load(f)

    inserted = 0
    for item in schemes_data:
        scheme = SchemeModel(
            scheme_id=item.get("scheme_id"),
            name=item.get("name"),
            category=item.get("category"),
            description=item.get("description"),
            min_age=item.get("min_age", 0),
            max_age=item.get("max_age", 120),
            max_annual_income=item.get("max_annual_income"),
            eligible_occupations=item.get("eligible_occupations", []),
            eligible_states=item.get("eligible_states", ["All"]),
            eligible_education=item.get("eligible_education", ["Any"]),
            gender_restriction=item.get("gender_restriction", "Any"),
            benefits=item.get("benefits", ""),
            portal_url=item.get("portal_url", ""),
            tags=item.get("tags", [])
        )
        db.add(scheme)
        inserted += 1

    db.commit()
    logger.info(f"Successfully seeded {inserted} schemes into database.")
    return inserted


def init_db():
    """Initializes tables and seeds default schemes."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_schemes_if_needed(db)


if __name__ == "__main__":
    init_db()
    print("Database initialized and seeded successfully.")
