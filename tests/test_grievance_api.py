"""
Tests for the mock Grievance Management API (Step 2).

Run with: pytest tests/test_grievance_api.py -v
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.models import grievance  # noqa: F401 (registers the model with Base)

# A dedicated engine for this file, wired in via dependency_overrides rather
# than the DATABASE_URL env var. The env-var approach works when this file
# runs alone, but app.core.config.settings and app.core.database's engine
# are process-wide singletons created on first import — when multiple test
# files that each use TestClient(app) run in the same pytest session (e.g.
# `pytest tests/`), only the first one's env var actually takes effect, and
# the rest silently share that same database. dependency_overrides sidesteps
# this entirely: each file gets a real, isolated engine regardless of import
# order or what any other test file does.
TEST_DB_PATH = "./test_grievance.db"
_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
_TestSessionLocal = sessionmaker(bind=_engine)


def _override_get_db():
    db = _TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=_engine)
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def test_health_check(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_categories(client):
    r = client.get("/api/grievance/categories")
    assert r.status_code == 200
    categories = r.json()["categories"]
    assert "Hostel" in categories
    assert "Harassment / Sensitive" in categories


def test_create_and_fetch_grievance(client):
    payload = {
        "student_id": "GBU2023CS101",
        "student_email": "student@gbu.ac.in",
        "category": "IT Infrastructure",
        "description": "Wifi has not worked in Block C for a week.",
        "location": "Block C, Room 214",
    }
    r = client.post("/api/grievance", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["ticket_id"].startswith("GBU-")
    assert data["status"] == "Pending"
    assert data["is_sensitive"] is False

    ticket_id = data["ticket_id"]
    r2 = client.get(f"/api/grievance/{ticket_id}")
    assert r2.status_code == 200
    assert r2.json()["ticket_id"] == ticket_id


def test_status_update_triggers_notification(client):
    payload = {
        "student_id": "GBU2023CS102",
        "student_email": "student2@gbu.ac.in",
        "category": "Academic",
        "description": "My internal marks were not updated on the portal.",
    }
    ticket_id = client.post("/api/grievance", json=payload).json()["ticket_id"]

    r = client.patch(f"/api/grievance/{ticket_id}/status", json={"status": "Resolved"})
    assert r.status_code == 200
    assert r.json()["status"] == "Resolved"


def test_unknown_ticket_returns_404(client):
    r = client.get("/api/grievance/GBU-2026-000000")
    assert r.status_code == 404


def test_sensitive_category_is_auto_flagged(client):
    payload = {
        "student_id": "GBU2023CS103",
        "student_email": "student3@gbu.ac.in",
        "category": "Harassment / Sensitive",
        "description": "Reporting an incident that needs immediate staff attention.",
    }
    r = client.post("/api/grievance", json=payload)
    assert r.status_code == 201
    assert r.json()["is_sensitive"] is True


def test_invalid_payload_rejected(client):
    # Missing required fields entirely
    r = client.post("/api/grievance", json={"student_id": "X"})
    assert r.status_code == 422
