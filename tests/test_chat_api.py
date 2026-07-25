"""
Tests for Step 6 — the /chat HTTP endpoint that ties together the Grievance
API (Step 2), Knowledge Base/RAG (Step 3), Dialogue Manager (Step 4), and
LLM layer (Step 5) into the single entrypoint a frontend widget calls.

These deliberately go over real HTTP via TestClient rather than calling
handle_message directly (that's already covered in test_dialogue_manager.py)
— the point here is to verify the HTTP contract itself: session_id
generation/reuse, request validation, and that state actually persists
across separate HTTP calls sharing a session_id.

Run with: pytest tests/test_chat_api.py -v
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.core.session_store import clear_all
from app.models import grievance  # noqa: F401 (registers the model with Base)

# See the comment in test_grievance_api.py for why this uses
# dependency_overrides with its own engine rather than the DATABASE_URL env
# var: multiple test files using TestClient(app) in one pytest session would
# otherwise silently share whichever DB the first-imported file set up.
TEST_DB_PATH = "./test_chat_api.db"
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


@pytest.fixture(autouse=True)
def _reset_sessions():
    clear_all()
    yield


def test_first_message_without_session_id_generates_one(client):
    r = client.post("/api/chat", json={"message": "hi", "student_id": "STU001"})
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"]  # non-empty, server-generated
    assert "Submit a grievance" in data["reply"]
    assert data["done"] is False


def test_missing_student_id_is_rejected(client):
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 422


def test_empty_message_is_rejected(client):
    r = client.post("/api/chat", json={"message": "", "student_id": "STU001"})
    assert r.status_code == 422


def test_session_state_persists_across_separate_http_calls(client):
    """The core thing this endpoint has to get right: two separate HTTP
    requests sharing a session_id must continue the same conversation."""
    r1 = client.post("/api/chat", json={"message": "I want to file a complaint", "student_id": "STU002"})
    session_id = r1.json()["session_id"]
    assert "category" in r1.json()["reply"].lower()

    r2 = client.post("/api/chat", json={
        "session_id": session_id, "message": "Academic", "student_id": "STU002",
    })
    assert "describe" in r2.json()["reply"].lower()
    # Same session_id echoed back, proving continuity rather than a fresh one.
    assert r2.json()["session_id"] == session_id


def test_different_session_ids_do_not_share_state(client):
    """Two different sessions started concurrently must not bleed into each other."""
    r1 = client.post("/api/chat", json={"message": "I want to file a complaint", "student_id": "STU003"})
    sid1 = r1.json()["session_id"]

    r2 = client.post("/api/chat", json={"message": "hi", "student_id": "STU004"})
    sid2 = r2.json()["session_id"]
    assert sid1 != sid2

    # Continuing session 1 with a category should not be affected by session 2's greeting.
    r3 = client.post("/api/chat", json={"session_id": sid1, "message": "Hostel", "student_id": "STU003"})
    assert "describe" in r3.json()["reply"].lower()


def test_full_submit_flow_over_http_creates_real_ticket(client):
    r1 = client.post("/api/chat", json={
        "message": "My hostel wifi has not worked for a week", "student_id": "STU005",
    })
    sid = r1.json()["session_id"]

    r2 = client.post("/api/chat", json={"session_id": sid, "message": "Block C, Room 214", "student_id": "STU005"})
    assert "email" in r2.json()["reply"].lower()

    r3 = client.post("/api/chat", json={"session_id": sid, "message": "student@gbu.ac.in", "student_id": "STU005"})
    assert "Shall I submit this" in r3.json()["reply"]

    r4 = client.post("/api/chat", json={"session_id": sid, "message": "yes", "student_id": "STU005"})
    data = r4.json()
    assert data["done"] is True
    assert data["ticket_id"].startswith("GBU-")

    # Track it via a brand-new session, proving the ticket is really persisted.
    r5 = client.post("/api/chat", json={
        "message": f"status of {data['ticket_id']}", "student_id": "STU006",
    })
    assert data["ticket_id"] in r5.json()["reply"]
    assert "Pending" in r5.json()["reply"]


def test_pre_filled_student_email_skips_email_question(client):
    r1 = client.post("/api/chat", json={
        "message": "My hostel wifi has not worked for a week",
        "student_id": "STU007",
        "student_email": "prefilled@gbu.ac.in",
    })
    sid = r1.json()["session_id"]

    r2 = client.post("/api/chat", json={"session_id": sid, "message": "Block C, Room 214", "student_id": "STU007"})
    # Email was pre-filled, so this should go straight to confirmation, not ask for email.
    assert "Shall I submit this" in r2.json()["reply"]
    assert "prefilled@gbu.ac.in" in r2.json()["reply"]


def test_harassment_escalates_over_http(client):
    r = client.post("/api/chat", json={
        "message": "someone is harassing me in my hostel block", "student_id": "STU008",
    })
    data = r.json()
    assert data["escalated"] is True
    assert data["done"] is True


def test_message_too_long_is_rejected(client):
    r = client.post("/api/chat", json={"message": "x" * 2001, "student_id": "STU009"})
    assert r.status_code == 422
