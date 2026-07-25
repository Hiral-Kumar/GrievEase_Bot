"""
Integration tests for Step 5 — verifying the Dialogue Manager actually uses
the LLM layer when rule-based matching fails, and still falls back correctly
when the LLM also can't help. Uses a mocked llm_client (no real API key is
available in this environment) so these exercise the real wiring between
dialogue_manager.py and llm_client.py, not just llm_client in isolation
(see test_llm_client.py for that).

Run with: pytest tests/test_dialogue_manager_llm_integration.py -v
"""
import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_dialogue_llm.db")

from app.core.database import Base  # noqa: E402
from app.core.dialogue_manager import handle_message  # noqa: E402
from app.core.session_store import clear_all  # noqa: E402
from app.services.llm_client import ExtractedSlots  # noqa: E402
from app.models.grievance import GrievanceCategory  # noqa: E402
from app.models import grievance  # noqa: E402,F401

TEST_DB_PATH = "./test_dialogue_llm.db"
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


def new_sid() -> str:
    return f"llm-test-{uuid.uuid4()}"


def test_paraphrased_complaint_uses_llm_extraction_when_rules_miss(db):
    """
    'the projector in my lecture hall hasn't worked all semester' shares no
    keyword with any bucket in intent_router._CATEGORY_KEYWORDS, so the
    rule-based classify_category returns None. With the LLM mocked to
    return IT Infrastructure, the bot should skip the category menu
    entirely and go straight to asking for location — proving the LLM
    fallback is actually wired in, not just present in the codebase.
    """
    sid = new_sid()
    fake_result = ExtractedSlots(
        category=GrievanceCategory.IT_INFRASTRUCTURE,
        description="The lecture hall projector has not worked all semester.",
    )
    with patch("app.core.dialogue_manager.llm_client.extract_slots", return_value=fake_result):
        r = handle_message(
            db, sid, "the projector in my lecture hall hasn't worked all semester",
            student_id="LLMSTU001",
        )
    assert "IT Infrastructure" in r.reply
    assert "category" not in r.reply.lower()  # should NOT have fallen back to the menu
    assert not r.done


def test_llm_unavailable_falls_back_to_not_sure_prompt(db):
    """
    When rule-based routing lands on FAQ (no submit-trigger word, no
    keyword-matched category), RAG finds nothing, AND the LLM also can't
    extract a category (e.g. no API key configured), the correct behavior
    is the generic "I'm not sure" fallback — NOT assuming submission intent
    and jumping to the category menu, since nothing in the conversation
    actually signaled that yet.
    """
    sid = new_sid()
    with patch("app.core.dialogue_manager.llm_client.extract_slots", return_value=None):
        r = handle_message(
            db, sid, "the projector in my lecture hall hasn't worked all semester",
            student_id="LLMSTU002",
        )
    assert "not sure" in r.reply.lower()
    assert not r.done


def test_category_step_uses_llm_extraction_for_freeform_answer(db):
    """
    During the CATEGORY retry step, if the student answers with a full
    sentence instead of a bare category name, LLM extraction should both
    resolve the category AND capture the description, skipping straight to
    the location question instead of asking them to describe it again.
    """
    sid = new_sid()
    handle_message(db, sid, "I want to file a complaint", student_id="LLMSTU003")

    fake_result = ExtractedSlots(
        category=GrievanceCategory.EXAMINATION,
        description="My exam re-evaluation request was never processed.",
    )
    with patch("app.core.dialogue_manager.llm_client.extract_slots", return_value=fake_result):
        r = handle_message(
            db, sid, "my re-evaluation request from last semester was never looked at",
            student_id="LLMSTU003",
        )
    assert "Examination" in r.reply
    assert "location" in r.reply.lower()
    assert "describe" not in r.reply.lower()  # should skip re-asking for description


def test_faq_uses_llm_synthesis_when_available(db):
    sid = new_sid()
    with patch("app.core.dialogue_manager.llm_client.synthesize_faq_answer",
               return_value="Most grievances are resolved within about a week."):
        r = handle_message(db, sid, "how long does resolution usually take", student_id="LLMSTU004")
    assert r.reply == "Most grievances are resolved within about a week."


def test_faq_falls_back_to_raw_kb_chunk_when_llm_unavailable(db):
    sid = new_sid()
    with patch("app.core.dialogue_manager.llm_client.synthesize_faq_answer", return_value=None):
        r = handle_message(db, sid, "how long does resolution usually take", student_id="LLMSTU005")
    # Falls back to Step 3's raw KB content — still a correct answer, just less polished.
    assert "working day" in r.reply.lower() or "working days" in r.reply.lower()
