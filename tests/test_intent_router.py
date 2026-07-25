"""
Tests for Step 4's rule-based intent classifier (app/core/intent_router.py).

Includes regression tests for two real classification bugs found and fixed
during development:
  1. Implicit complaints (stating a problem, not asking to "file" one) must
     still be recognized as Submit Grievance — this is the exact pattern
     used in the Day 1 docs' own sample dialogue.
  2. A question *about* the grievance process must not be misclassified as
     Submit just because it contains a trigger word like "grievance".
"""
import pytest

from app.core.intent_router import classify_intent, classify_category, extract_ticket_id, Intent
from app.models.grievance import GrievanceCategory


@pytest.mark.parametrize("message,expected", [
    ("hi", Intent.GREETING),
    ("hello there", Intent.GREETING),
    ("I want to file a complaint", Intent.SUBMIT_GRIEVANCE),
    ("my wifi has not worked for a week", Intent.SUBMIT_GRIEVANCE),
    ("my hostel wifi has not worked for a week", Intent.SUBMIT_GRIEVANCE),
    ("I submitted a complaint about my marks last week", Intent.SUBMIT_GRIEVANCE),
    ("what is the status of GBU-2026-004821", Intent.TRACK_STATUS),
    ("track my ticket", Intent.TRACK_STATUS),
    ("someone is harassing me", Intent.ESCALATE),
    ("I want to report ragging in my hostel", Intent.ESCALATE),
    ("cancel", Intent.CANCEL),
    ("how long does resolution take", Intent.FAQ),
    ("does the IT cell handle printer issues", Intent.FAQ),
    ("can I edit my grievance after submitting", Intent.FAQ),
    ("what is the weather today", Intent.FAQ),
])
def test_classify_intent(message, expected):
    assert classify_intent(message) == expected


def test_extract_ticket_id_case_insensitive():
    assert extract_ticket_id("please check gbu-2026-004821 for me") == "GBU-2026-004821"
    assert extract_ticket_id("no ticket mentioned here") is None


@pytest.mark.parametrize("message,expected", [
    ("my hostel wifi has not worked for a week", GrievanceCategory.HOSTEL),
    ("my internal marks are wrong", GrievanceCategory.ACADEMIC),
    ("I need my transcript for a scholarship", GrievanceCategory.ADMINISTRATIVE),
    ("the professor never replies to emails", GrievanceCategory.FACULTY),
    ("someone is ragging juniors in the hostel", GrievanceCategory.HARASSMENT_SENSITIVE),
    ("random unrelated text about nothing specific", None),
])
def test_classify_category(message, expected):
    assert classify_category(message) == expected
