"""
Dialogue Manager — the "Dialogue Manager" box in the architecture diagram
(Day 1 docs, Fig. 1). Orchestrates the two data-critical, slot-filling flows
(Submit Grievance, Track Status) plus routing to FAQ/escalation, using the
rule-based intent classifier from Step 4. Step 5 adds an LLM layer on top for
free-text slot extraction and richer FAQ answers — this module is written so
that layer plugs in without restructuring the state machine itself.
"""
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.intent_router import Intent, classify_intent, classify_category, extract_ticket_id
from app.core.session_store import ConversationState, Flow, SubmitStep, get_state, save_state, reset_state
from app.models.grievance import GrievanceCategory
from app.services import grievance_service as svc
from app.services import llm_client
from app.services.rag_service import build_rag_context

MENU_TEXT = (
    "Hi! I'm GrievEase Bot 🤖 — I can help you:\n"
    "  1. Submit a grievance\n"
    "  2. Track a grievance by Ticket ID\n"
    "  3. Answer questions about the grievance process\n"
    "What would you like to do?"
)

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_AFFIRMATIVE = {"yes", "yeah", "yep", "correct", "confirm", "submit", "sure", "ok", "okay", "y"}
_NEGATIVE = {"no", "nope", "wrong", "incorrect", "cancel", "n"}
_SKIP_WORDS = {"skip", "none", "n/a", "na", "no location", "not applicable"}

MAX_RETRIES = 3


@dataclass
class DialogueResult:
    reply: str
    done: bool = False
    escalated: bool = False
    ticket_id: str | None = None


def _category_menu() -> str:
    return "\n".join(f"  - {c.value}" for c in GrievanceCategory)


def _match_category_by_name(message: str) -> GrievanceCategory | None:
    """Matches an exact/near-exact category name, for when the bot has just shown the list."""
    lowered = message.strip().lower()
    for c in GrievanceCategory:
        if c.value.lower() == lowered or c.value.lower() in lowered:
            return c
    return None


def handle_message(
    db: Session, session_id: str, message: str, *, student_id: str, student_email: str | None = None,
) -> DialogueResult:
    """
    Main entrypoint: advances the conversation for this session by one turn.
    `student_id` is assumed to come from an authenticated session (the
    Gateway layer's job, per docs Section 4.1) — the dialogue manager never
    trusts a student ID typed in chat as identity proof.
    """
    state = get_state(session_id)
    intent = classify_intent(message)

    # --- Global overrides: apply regardless of any active flow ---
    if intent == Intent.ESCALATE:
        reset_state(session_id)
        return DialogueResult(
            reply=(
                "I understand, and I want to make sure this gets the right attention. "
                "I'm connecting you with GBU IT Cell staff for direct follow-up — "
                "this has been flagged for priority review."
            ),
            escalated=True, done=True,
        )

    if intent == Intent.CANCEL and state.flow != Flow.NONE:
        reset_state(session_id)
        return DialogueResult(reply="No problem, I've cancelled that. Anything else I can help with?")

    # --- Active flow takes priority over fresh intent classification ---
    if state.flow == Flow.SUBMIT_GRIEVANCE:
        return _handle_submit_step(db, session_id, state, message, student_id, student_email)

    if state.flow == Flow.TRACK_STATUS:
        return _handle_track_step(session_id, state, message, db=db)

    # --- No active flow: route on fresh intent ---
    if intent == Intent.GREETING:
        return DialogueResult(reply=MENU_TEXT)

    if intent == Intent.SUBMIT_GRIEVANCE:
        return _start_submit_flow(session_id, state, message, student_email)

    if intent == Intent.TRACK_STATUS:
        ticket_id = extract_ticket_id(message)
        if ticket_id:
            return _lookup_ticket(db, ticket_id)
        state.flow = Flow.TRACK_STATUS
        save_state(session_id, state)
        return DialogueResult(reply="Sure — what's your Ticket ID? (format: GBU-YYYY-XXXXXX)")

    if intent == Intent.FAQ:
        rag_result = build_rag_context(message, top_k=3)
        if rag_result.has_answer:
            return _answer_from_rag(message, rag_result)

        # No FAQ/KB match. Before giving up, double-check with the LLM
        # whether this message is actually an unrecognized complaint rather
        # than a genuine off-topic question — e.g. "the projector in my
        # lecture hall hasn't worked all semester" has no submit-trigger
        # word and no keyword-matched category, so classify_intent landed
        # on FAQ by elimination, not by confidently deciding it's a
        # question. This is the correct point to consult the LLM: it's
        # cheap to only call it on the FAQ-miss path, and it's exactly the
        # ambiguous case the rule-based layer can't resolve alone (see
        # docs, Section 3.1 — the LLM augments routing, it doesn't replace it).
        extracted = llm_client.extract_slots(message)
        if extracted is not None and extracted.category is not None:
            return _start_submit_flow(session_id, state, message, student_email, pre_extracted=extracted)

        return DialogueResult(
            reply=(
                "I'm not sure about that one. Would you like me to connect you with "
                "IT Cell staff, or would you like to submit/track a grievance instead?"
            )
        )

    return DialogueResult(reply="I'm not sure I follow. " + MENU_TEXT)


# ---------------------------------------------------------------------------
# Submit Grievance flow
# ---------------------------------------------------------------------------

def _start_submit_flow(
    session_id: str, state: ConversationState, message: str, student_email: str | None,
    pre_extracted: "llm_client.ExtractedSlots | None" = None,
) -> DialogueResult:
    state.flow = Flow.SUBMIT_GRIEVANCE
    if student_email:
        state.slots["email"] = student_email

    # Implicit-complaint fast path: if the opening message already names a
    # category (e.g. "my hostel wifi has not worked for a week"), treat it as
    # both the category signal and the description, and skip straight to
    # asking for location — mirrors the Day 1 docs' own sample dialogue,
    # where the bot doesn't re-ask for information already given.
    category = classify_category(message)
    description = message.strip()

    if category is None:
        # If the caller already ran LLM extraction (the FAQ-miss path in
        # handle_message), reuse that result instead of calling the API
        # again for the same message.
        extracted = pre_extracted if pre_extracted is not None else llm_client.extract_slots(message)
        if extracted is not None:
            category = extracted.category
            description = extracted.description or description

    if category:
        state.slots["category"] = category
        state.slots["description"] = description
        state.step = SubmitStep.LOCATION
        save_state(session_id, state)
        return DialogueResult(
            reply=(
                f"I'm sorry to hear that. I'll file this under {category.value}. "
                f"Could you share a specific location or department (e.g. hostel block/room), "
                f"or type 'skip' if not applicable?"
            )
        )

    state.step = SubmitStep.CATEGORY
    save_state(session_id, state)
    return DialogueResult(
        reply="I can help you submit that. Which category best fits your issue?\n" + _category_menu()
    )


def _handle_submit_step(
    db: Session, session_id: str, state: ConversationState, message: str,
    student_id: str, student_email: str | None,
) -> DialogueResult:
    step = state.step

    if step == SubmitStep.CATEGORY:
        category = _match_category_by_name(message) or classify_category(message)
        description_override = None
        if not category:
            extracted = llm_client.extract_slots(message)
            if extracted is not None:
                category = extracted.category
                description_override = extracted.description
        if not category:
            state.retry_count += 1
            if state.retry_count >= MAX_RETRIES:
                reset_state(session_id)
                return DialogueResult(
                    reply="I'm having trouble matching that to a category — let me connect you with a staff member instead.",
                    escalated=True, done=True,
                )
            save_state(session_id, state)
            return DialogueResult(reply="Sorry, I didn't catch that. Please pick one:\n" + _category_menu())

        state.slots["category"] = category
        # If the LLM extracted a usable description from this same message
        # (e.g. the student described the problem instead of naming a bare
        # category), use it and skip straight to location instead of asking
        # them to repeat themselves.
        if description_override:
            state.slots["description"] = description_override
            state.step = SubmitStep.LOCATION
            state.retry_count = 0
            save_state(session_id, state)
            return DialogueResult(reply=f"Got it — {category.value}. Any specific location or department? (or type 'skip')")

        state.step = SubmitStep.DESCRIPTION
        state.retry_count = 0
        save_state(session_id, state)
        return DialogueResult(reply=f"Got it — {category.value}. Could you briefly describe the issue?")

    if step == SubmitStep.DESCRIPTION:
        if len(message.strip()) < 10:
            state.retry_count += 1
            if state.retry_count >= MAX_RETRIES:
                reset_state(session_id)
                return DialogueResult(
                    reply="Let's get you to a staff member who can note this down directly.",
                    escalated=True, done=True,
                )
            save_state(session_id, state)
            return DialogueResult(reply="Could you add a little more detail so the right team can act on it?")

        state.slots["description"] = message.strip()
        state.step = SubmitStep.LOCATION
        state.retry_count = 0
        save_state(session_id, state)
        return DialogueResult(reply="Any specific location or department? (or type 'skip')")

    if step == SubmitStep.LOCATION:
        state.slots["location"] = None if message.strip().lower() in _SKIP_WORDS else message.strip()
        if state.slots.get("email"):
            return _move_to_confirm(session_id, state)
        state.step = SubmitStep.EMAIL
        save_state(session_id, state)
        return DialogueResult(reply="What email should I send your confirmation and status updates to?")

    if step == SubmitStep.EMAIL:
        if not _EMAIL_PATTERN.match(message.strip()):
            state.retry_count += 1
            if state.retry_count >= MAX_RETRIES:
                reset_state(session_id)
                return DialogueResult(
                    reply="Let's get a staff member to help complete this submission.",
                    escalated=True, done=True,
                )
            save_state(session_id, state)
            return DialogueResult(reply="That doesn't look like a valid email — could you re-enter it?")
        state.slots["email"] = message.strip()
        return _move_to_confirm(session_id, state)

    if step == SubmitStep.CONFIRM:
        lowered = message.strip().lower()
        if lowered in _AFFIRMATIVE:
            grievance = svc.create_grievance(
                db, student_id=student_id, student_email=state.slots["email"],
                category=state.slots["category"], description=state.slots["description"],
                location=state.slots.get("location"),
            )
            reset_state(session_id)
            return DialogueResult(
                reply=(
                    f"Your grievance has been submitted. Your Ticket ID is {grievance.ticket_id}. "
                    f"You'll get an email confirmation, and you can ask me for updates anytime using this ID."
                ),
                done=True, ticket_id=grievance.ticket_id,
            )
        if lowered in _NEGATIVE:
            reset_state(session_id)
            return DialogueResult(reply="No problem, I've cancelled that. Would you like to start over or do something else?")
        return DialogueResult(reply="Just to confirm — should I go ahead and submit this? (yes/no)")

    # Shouldn't normally be reached; defensive fallback.
    reset_state(session_id)
    return DialogueResult(reply="Something went off track — let's start again. " + MENU_TEXT)


def _move_to_confirm(session_id: str, state: ConversationState) -> DialogueResult:
    state.step = SubmitStep.CONFIRM
    save_state(session_id, state)
    slots = state.slots
    location_line = f"\nLocation: {slots['location']}" if slots.get("location") else ""
    summary = (
        f"Here's a summary:\n"
        f"Category: {slots['category'].value}\n"
        f"Issue: {slots['description']}"
        f"{location_line}\n"
        f"Email: {slots['email']}\n"
        f"Shall I submit this? (yes/no)"
    )
    return DialogueResult(reply=summary)


# ---------------------------------------------------------------------------
# Track Status flow
# ---------------------------------------------------------------------------

def _handle_track_step(session_id: str, state: ConversationState, message: str, *, db: Session) -> DialogueResult:
    ticket_id = extract_ticket_id(message)
    if not ticket_id:
        state.retry_count += 1
        if state.retry_count >= MAX_RETRIES:
            reset_state(session_id)
            return DialogueResult(
                reply="Let's get a staff member to help locate your ticket.",
                escalated=True, done=True,
            )
        save_state(session_id, state)
        return DialogueResult(reply="That doesn't look like a valid Ticket ID. Format: GBU-YYYY-XXXXXX — could you re-check it?")

    reset_state(session_id)
    return _lookup_ticket(db, ticket_id)


def _lookup_ticket(db: Session, ticket_id: str) -> DialogueResult:
    try:
        grievance = svc.get_grievance_by_ticket_id(db, ticket_id)
    except svc.GrievanceNotFound:
        return DialogueResult(
            reply=f"I couldn't find a grievance with Ticket ID {ticket_id}. Could you double-check the ID?",
            done=True,
        )
    return DialogueResult(
        reply=(
            f"Your grievance {grievance.ticket_id} ({grievance.category.value}) "
            f"is currently {grievance.status.value}. Last updated: "
            f"{grievance.updated_at.strftime('%d %b %Y')}."
        ),
        done=True, ticket_id=grievance.ticket_id,
    )


# ---------------------------------------------------------------------------
# FAQ
# ---------------------------------------------------------------------------

def _answer_from_rag(message: str, result) -> DialogueResult:
    """
    Turns an already-retrieved RAG result into a reply: LLM synthesis first
    (a natural answer grounded in all retrieved chunks), falling back to the
    single best raw chunk verbatim if no API key is configured or the call
    fails — see llm_client.py. Either way the answer is grounded only in
    retrieved KB content, never in the model's own unverified knowledge.
    """
    synthesized = llm_client.synthesize_faq_answer(message, result.context_text)
    if synthesized:
        return DialogueResult(reply=synthesized)
    top_source = result.sources[0]
    return DialogueResult(reply=f"{top_source.content}")
