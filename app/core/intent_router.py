"""
Intent recognition — the "Intent Recognition" box from the architecture
diagram (Day 1 docs, Fig. 1). This is a rule-based classifier so the
dialogue manager can be built and fully tested without needing an LLM API
key; Step 5 layers Claude on top for messages this layer can't confidently
classify, rather than replacing it — the rule-based path stays as a fast,
reliable first pass for the two data-critical intents (Submit, Track).
"""
import enum
import re

from app.knowledge_base.retriever import tokenize_and_stem
from app.models.grievance import GrievanceCategory


class Intent(str, enum.Enum):
    GREETING = "greeting"
    SUBMIT_GRIEVANCE = "submit_grievance"
    TRACK_STATUS = "track_status"
    FAQ = "faq"
    ESCALATE = "escalate"
    CANCEL = "cancel"
    UNKNOWN = "unknown"


TICKET_ID_PATTERN = re.compile(r"\bGBU-\d{4}-\d{6}\b", re.IGNORECASE)

_GREETING_WORDS = {"hi", "hello", "hey", "menu", "start", "help"}
_CANCEL_WORDS = {"cancel", "stop", "nevermind", "quit", "exit"}

_SUBMIT_TRIGGERS = {
    "submit", "file", "report", "complain", "complaint", "grievance",
    "issue", "problem", "raise", "log",
}
_TRACK_TRIGGERS = {
    "track", "status", "update", "progress", "check",
}

# If a message opens with one of these, it reads as a genuine question
# ("How long does resolution take?"), not a statement of a problem. This
# matters for the implicit-complaint check below: without it, a question
# like "does the IT cell handle printer issues?" would be misclassified as
# a new grievance just because it mentions a category keyword.
_QUESTION_STARTERS = {
    "how", "what", "why", "can", "could", "does", "do", "is", "are",
    "will", "would", "should", "when", "where",
}

# Safety-critical trigger words — mirrors the retriever's safety override
# (app/knowledge_base/retriever.py). Kept as a separate constant here (rather
# than importing the private one) since intent-level escalation and
# KB-retrieval boosting are conceptually distinct call sites, even though the
# word list overlaps.
_SAFETY_TRIGGER_STEMS = frozenset({
    "harass", "rag", "abus", "assault", "threat", "unsaf", "bulli", "discrimin",
})

# Keyword -> category, used for auto-classifying free-text descriptions
# during the Submit Grievance flow. Checked in this priority order so that,
# e.g., "wifi in my hostel room" resolves to Hostel rather than IT
# Infrastructure. Harassment is checked first, before anything else, since a
# safety-relevant category should never be silently reclassified as
# something more mundane just because another keyword also matched.
_CATEGORY_KEYWORDS: list[tuple[GrievanceCategory, set[str]]] = [
    (GrievanceCategory.HARASSMENT_SENSITIVE, {"harass", "rag", "discrimin", "assault", "bulli", "unsaf"}),
    (GrievanceCategory.HOSTEL, {"hostel", "room", "mess", "warden", "roommat", "block"}),
    (GrievanceCategory.EXAMINATION, {"exam", "reevalu", "admit", "seat", "invigil"}),
    (GrievanceCategory.ACADEMIC, {"mark", "grade", "attend", "registr", "cours", "academ"}),
    (GrievanceCategory.FACULTY, {"faculti", "professor", "teacher"}),
    (GrievanceCategory.ADMINISTRATIVE, {"certif", "transcript", "fee", "scholarship", "receipt"}),
    (GrievanceCategory.IT_INFRASTRUCTURE, {"wifi", "internet", "portal", "login", "printer", "lab", "websit"}),
]


def extract_ticket_id(message: str) -> str | None:
    match = TICKET_ID_PATTERN.search(message)
    return match.group(0).upper() if match else None


def classify_category(message: str) -> GrievanceCategory | None:
    """Best-effort category guess from free text; returns None if nothing matches (caller should ask)."""
    tokens = set(tokenize_and_stem(message))
    for category, keywords in _CATEGORY_KEYWORDS:
        if tokens & keywords:
            return category
    return None


def classify_intent(message: str) -> Intent:
    """
    Rule-based first-pass intent classification. Order matters: safety and
    ticket-ID detection are checked before the generic keyword buckets, since
    those are the highest-consequence and highest-precision signals
    respectively.
    """
    tokens = set(tokenize_and_stem(message))
    lowered = message.strip().lower()

    if tokens & _SAFETY_TRIGGER_STEMS:
        return Intent.ESCALATE

    if extract_ticket_id(message):
        return Intent.TRACK_STATUS

    if lowered in _CANCEL_WORDS or tokens & _CANCEL_WORDS:
        return Intent.CANCEL

    if lowered in _GREETING_WORDS or (tokens & _GREETING_WORDS and len(tokens) <= 2):
        return Intent.GREETING

    if tokens & _TRACK_TRIGGERS:
        return Intent.TRACK_STATUS

    # Question-gate: a message phrased as a question about grievances in
    # general (e.g. "can I edit my grievance after submitting?") should stay
    # FAQ even though it contains a submit-trigger word like "grievance" —
    # only a statement reporting an actual problem should start the Submit
    # flow. This check covers both the explicit trigger-word case and the
    # implicit-complaint case below with one rule, rather than two
    # inconsistent ones.
    first_word = lowered.split()[0] if lowered.split() else ""
    looks_like_question = message.strip().endswith("?") or first_word in _QUESTION_STARTERS

    if not looks_like_question:
        if tokens & _SUBMIT_TRIGGERS:
            return Intent.SUBMIT_GRIEVANCE
        # Implicit complaint: a statement (not a question) that names a
        # recognizable grievance category — e.g. "my hostel wifi has not
        # worked for a week" — reads as reporting a problem even without an
        # explicit "I want to file/submit/report" verb. This is the exact
        # pattern used in the Day 1 docs' own sample dialogue, so it's
        # treated as a first-class case: real students describe problems,
        # they don't file paperwork requests.
        if classify_category(message) is not None:
            return Intent.SUBMIT_GRIEVANCE

    return Intent.FAQ
