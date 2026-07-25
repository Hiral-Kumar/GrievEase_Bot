"""
Database engine + session management.

Using SQLite for this prototype keeps setup zero-config for evaluators — no external
DB server needed to run the project. The models are plain SQLAlchemy, so swapping
DATABASE_URL to a Postgres/MySQL connection string for a real deployment is a
one-line change, not a rewrite.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# Ensure the data directory exists before SQLite tries to create the file there.
os.makedirs("app/data", exist_ok=True)

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and guarantees it's closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called once on app startup."""
    from app.models import grievance  # noqa: F401 (ensures model is registered)
    Base.metadata.create_all(bind=engine)
