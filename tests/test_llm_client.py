"""
Tests for Step 5 — the LLM Reasoning Layer (app/services/llm_client.py).

No real ANTHROPIC_API_KEY is available in this environment, so these tests
mock the Anthropic client at the API boundary (`_get_client`) rather than
making real network calls. This verifies two things that matter regardless
of whether a real key is ever configured:
  1. Graceful degradation — every function returns None cleanly when no key
     is set, or when the client/response is broken in some way.
  2. Correct behavior when the LLM DOES respond — JSON parsing, category
     validation, and prompt content.

Run with: pytest tests/test_llm_client.py -v
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import app.services.llm_client as llm_client
from app.models.grievance import GrievanceCategory


def _fake_response(text: str):
    """Mimics the shape of an Anthropic Message response enough for _call_claude to parse it."""
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    """Stands in for anthropic.Anthropic — records calls, returns a canned response."""
    def __init__(self, reply_text: str | None = None, raise_error: bool = False):
        self.reply_text = reply_text
        self.raise_error = raise_error
        self.last_call_kwargs = None

        class _Messages:
            def create(inner_self, **kwargs):
                self.last_call_kwargs = kwargs
                if self.raise_error:
                    raise RuntimeError("simulated API failure")
                return _fake_response(self.reply_text)

        self.messages = _Messages()


def _reset_client_cache():
    """The client is a lazy module-level singleton — reset it between tests."""
    llm_client._client = None
    llm_client._client_init_attempted = False


# ---------------------------------------------------------------------------
# Graceful degradation — no API key configured (the actual state of this repo)
# ---------------------------------------------------------------------------

def test_no_api_key_disables_llm_layer():
    _reset_client_cache()
    with patch.object(llm_client.settings, "ANTHROPIC_API_KEY", ""):
        assert llm_client._get_client() is None
        assert llm_client.extract_slots("my hostel wifi is down") is None
        assert llm_client.synthesize_faq_answer("how long does this take?", "some context") is None


def test_client_init_failure_degrades_to_none():
    _reset_client_cache()
    with patch.object(llm_client.settings, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("anthropic.Anthropic", side_effect=RuntimeError("boom")):
        assert llm_client._get_client() is None


# ---------------------------------------------------------------------------
# Slot extraction — with a mocked client
# ---------------------------------------------------------------------------

def test_extract_slots_parses_valid_json_response():
    _reset_client_cache()
    fake = FakeClient(reply_text=json.dumps({
        "category": "IT Infrastructure",
        "description": "The lecture hall projector has not worked all semester.",
    }))
    with patch.object(llm_client, "_get_client", return_value=fake):
        result = llm_client.extract_slots("the projector in my lecture hall hasn't worked all semester")

    assert result is not None
    assert result.category == GrievanceCategory.IT_INFRASTRUCTURE
    assert "projector" in result.description.lower()


def test_extract_slots_handles_markdown_fenced_json():
    _reset_client_cache()
    fenced = "```json\n" + json.dumps({"category": "Hostel", "description": "Mess food quality is poor."}) + "\n```"
    fake = FakeClient(reply_text=fenced)
    with patch.object(llm_client, "_get_client", return_value=fake):
        result = llm_client.extract_slots("the mess food has been bad all week")

    assert result is not None
    assert result.category == GrievanceCategory.HOSTEL


def test_extract_slots_returns_none_for_invalid_category():
    _reset_client_cache()
    fake = FakeClient(reply_text=json.dumps({"category": "Not A Real Category", "description": "something"}))
    with patch.object(llm_client, "_get_client", return_value=fake):
        assert llm_client.extract_slots("some ambiguous message") is None


def test_extract_slots_returns_none_for_malformed_json():
    _reset_client_cache()
    fake = FakeClient(reply_text="this is not json at all")
    with patch.object(llm_client, "_get_client", return_value=fake):
        assert llm_client.extract_slots("some message") is None


def test_extract_slots_returns_none_when_category_is_null():
    _reset_client_cache()
    fake = FakeClient(reply_text=json.dumps({"category": None, "description": None}))
    with patch.object(llm_client, "_get_client", return_value=fake):
        assert llm_client.extract_slots("hello there") is None


def test_extract_slots_returns_none_on_api_error():
    _reset_client_cache()
    fake = FakeClient(raise_error=True)
    with patch.object(llm_client, "_get_client", return_value=fake):
        assert llm_client.extract_slots("some message") is None


def test_extract_slots_prompt_includes_all_categories():
    _reset_client_cache()
    fake = FakeClient(reply_text=json.dumps({"category": "Academic", "description": "x"}))
    with patch.object(llm_client, "_get_client", return_value=fake):
        llm_client.extract_slots("my marks are wrong")

    sent_prompt = fake.last_call_kwargs["messages"][0]["content"]
    for category in GrievanceCategory:
        assert category.value in sent_prompt


# ---------------------------------------------------------------------------
# FAQ synthesis
# ---------------------------------------------------------------------------

def test_synthesize_faq_answer_returns_llm_text():
    _reset_client_cache()
    fake = FakeClient(reply_text="Most grievances resolve within 3-7 working days.")
    with patch.object(llm_client, "_get_client", return_value=fake):
        answer = llm_client.synthesize_faq_answer(
            "how long does this take?",
            "[Resolution time] Grievances are resolved within 3-7 working days.",
        )
    assert "3-7 working days" in answer


def test_synthesize_faq_answer_none_on_error():
    _reset_client_cache()
    fake = FakeClient(raise_error=True)
    with patch.object(llm_client, "_get_client", return_value=fake):
        assert llm_client.synthesize_faq_answer("question", "context") is None


def test_synthesize_faq_prompt_includes_context_and_question():
    _reset_client_cache()
    fake = FakeClient(reply_text="an answer")
    with patch.object(llm_client, "_get_client", return_value=fake):
        llm_client.synthesize_faq_answer("How long does resolution take?", "[Topic] Some KB content here.")

    sent_prompt = fake.last_call_kwargs["messages"][0]["content"]
    assert "How long does resolution take?" in sent_prompt
    assert "Some KB content here." in sent_prompt
