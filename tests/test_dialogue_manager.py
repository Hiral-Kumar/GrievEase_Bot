"""
Tests for Step 4 — the Dialogue Manager (Submit Grievance + Track Status
flows, escalation, cancellation, and interim FAQ handling).

Run with: pytest tests/test_dialogue_manager.py -v
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_dialogue.db")

from app.core.database import Base  # noqa: E402
from app.core.dialogue_manager import handle_message  # noqa: E402
from app.core.session_store import clear_all  # noqa: E402
from app.models import grievance  # noqa: E402,F401 (registers the model)

TEST_DB_PATH = "./test_dialogue_manager.db"
engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(bind=engine)


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture
def db():
    session = TestSessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _clear_sessions():
    clear_all()
    yield


def new_session_id() -> str:
    return f"test-{uuid.uuid4()}"


def test_greeting_shows_menu(db):
    r = handle_message(db, new_session_id(), "hi", student_id="GBU001")
    assert "Submit a grievance" in r.reply
    assert not r.done


def test_full_submit_flow_implicit_complaint(db):
    """Mirrors the exact sample dialogue from the Day 1 docs."""
    sid = new_session_id()
    r1 = handle_message(db, sid, "My hostel wifi has not worked for a week", student_id="GBU001")
    assert "Hostel" in r1.reply
    assert not r1.done

    r2 = handle_message(db, sid, "Block C, Room 214", student_id="GBU001")
    assert "email" in r2.reply.lower()

    r3 = handle_message(db, sid, "student@gbu.ac.in", student_id="GBU001")
    assert "Shall I submit this?" in r3.reply
    assert "Hostel" in r3.reply
    assert "Block C, Room 214" in r3.reply

    r4 = handle_message(db, sid, "yes", student_id="GBU001")
    assert r4.done is True
    assert r4.ticket_id is not None
    assert r4.ticket_id.startswith("GBU-")
    assert "Ticket ID is" in r4.reply


def test_submit_flow_with_explicit_category_selection(db):
    sid = new_session_id()
    r1 = handle_message(db, sid, "I want to file a complaint", student_id="GBU002")
    assert "category" in r1.reply.lower()

    r2 = handle_message(db, sid, "Academic", student_id="GBU002")
    assert "describe" in r2.reply.lower()

    r3 = handle_message(db, sid, "My internal marks were never updated on the portal", student_id="GBU002")
    assert "location" in r3.reply.lower()

    r4 = handle_message(db, sid, "skip", student_id="GBU002")
    assert "email" in r4.reply.lower()

    r5 = handle_message(db, sid, "student2@gbu.ac.in", student_id="GBU002")
    assert "Shall I submit this?" in r5.reply

    r6 = handle_message(db, sid, "yes", student_id="GBU002")
    assert r6.done is True
    assert r6.ticket_id is not None


def test_submit_flow_cancel_midway(db):
    sid = new_session_id()
    handle_message(db, sid, "I want to submit a grievance", student_id="GBU003")
    r = handle_message(db, sid, "cancel", student_id="GBU003")
    assert "cancelled" in r.reply.lower()
    assert r.done is False


def test_submit_flow_invalid_email_retry_then_success(db):
    sid = new_session_id()
    handle_message(db, sid, "my portal login is not working", student_id="GBU004")
    handle_message(db, sid, "skip", student_id="GBU004")
    r_invalid = handle_message(db, sid, "not-an-email", student_id="GBU004")
    assert "valid email" in r_invalid.reply.lower()

    r_valid = handle_message(db, sid, "valid@gbu.ac.in", student_id="GBU004")
    assert "Shall I submit this?" in r_valid.reply

    r_final = handle_message(db, sid, "yes", student_id="GBU004")
    assert r_final.done is True


def test_track_status_with_ticket_id_in_first_message(db):
    sid_submit = new_session_id()
    handle_message(db, sid_submit, "my hostel wifi is down", student_id="GBU005")
    handle_message(db, sid_submit, "skip", student_id="GBU005")
    handle_message(db, sid_submit, "trackme@gbu.ac.in", student_id="GBU005")
    r_created = handle_message(db, sid_submit, "yes", student_id="GBU005")
    ticket_id = r_created.ticket_id

    sid_track = new_session_id()
    r = handle_message(db, sid_track, f"what is the status of {ticket_id}", student_id="GBU005")
    assert ticket_id in r.reply
    assert "Pending" in r.reply
    assert r.done is True


def test_track_status_multiturn_without_ticket_upfront(db):
    sid = new_session_id()
    r1 = handle_message(db, sid, "track my grievance", student_id="GBU006")
    assert "Ticket ID" in r1.reply
    assert not r1.done

    r2 = handle_message(db, sid, "it's GBU-2026-000001", student_id="GBU006")
    # won't exist, but should attempt a clean lookup and report not-found
    assert "GBU-2026-000001" in r2.reply
    assert r2.done is True


def test_track_status_unknown_ticket(db):
    sid = new_session_id()
    r = handle_message(db, sid, "GBU-2026-555555", student_id="GBU007")
    assert "couldn't find" in r.reply.lower()
    assert r.done is True


def test_escalation_on_harassment_keyword(db):
    sid = new_session_id()
    r = handle_message(db, sid, "someone is ragging me in the hostel", student_id="GBU008")
    assert r.escalated is True
    assert r.done is True


def test_faq_returns_grounded_answer(db):
    sid = new_session_id()
    r = handle_message(db, sid, "how long does resolution usually take", student_id="GBU009")
    assert "working day" in r.reply.lower() or "working days" in r.reply.lower()
    assert not r.escalated


def test_faq_offtopic_offers_escalation_or_alternatives(db):
    sid = new_session_id()
    r = handle_message(db, sid, "what is the weather today", student_id="GBU010")
    assert "not sure" in r.reply.lower()
