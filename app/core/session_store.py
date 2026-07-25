"""
Conversation session store — tracks per-session dialogue state across turns
(the "Dialogue Manager" component from the architecture diagram, Fig. 1).

In-memory and process-local for this prototype: fine for a single-instance
demo/grading run. A real deployment would swap this for Redis (or a DB table)
keyed by session ID so state survives restarts and works across multiple app
instances — the interface below (`get`, `save`, `clear`) is small enough that
swapping the backing store later doesn't touch the dialogue manager's logic.
"""
import enum
from dataclasses import dataclass, field


class Flow(str, enum.Enum):
    NONE = "none"
    SUBMIT_GRIEVANCE = "submit_grievance"
    TRACK_STATUS = "track_status"


class SubmitStep(str, enum.Enum):
    CATEGORY = "category"
    DESCRIPTION = "description"
    LOCATION = "location"
    EMAIL = "email"
    CONFIRM = "confirm"


@dataclass
class ConversationState:
    flow: Flow = Flow.NONE
    step: str | None = None
    slots: dict = field(default_factory=dict)
    # Tracks how many times the bot has re-asked the same question without a
    # usable answer — used to trigger escalation instead of looping forever
    # on a confused student (see docs, Section 12 — Escalation Policy).
    retry_count: int = 0


_SESSIONS: dict[str, ConversationState] = {}


def get_state(session_id: str) -> ConversationState:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = ConversationState()
    return _SESSIONS[session_id]


def save_state(session_id: str, state: ConversationState) -> None:
    _SESSIONS[session_id] = state


def reset_state(session_id: str) -> None:
    _SESSIONS[session_id] = ConversationState()


def clear_all() -> None:
    """Testing helper — wipes all session state between test runs."""
    _SESSIONS.clear()
