"""
Chat endpoint schemas — the public contract for the single entrypoint a
frontend chat widget calls (Day 1 docs, Fig. 1: this is where the "Chatbot
Gateway / API Layer" meets the "Conversational AI Core").
"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = Field(
        None,
        description=(
            "Conversation session ID. Omit on the first message of a new "
            "conversation — the server generates one and returns it; the "
            "client must send that same ID on every subsequent message to "
            "keep the conversation's state (see docs, Section 4.1 — Gateway "
            "layer handles session management)."
        ),
    )
    message: str = Field(..., min_length=1, max_length=2000)

    # In a real deployment, student_id/email come from the Gateway layer's
    # authenticated session token (docs, Section 4.1 & 12.1) — the chatbot
    # never trusts an identity claim typed in chat. This prototype accepts
    # them directly in the request body to stand in for that auth layer
    # without building a full login system, which is out of scope for the
    # screening challenge. A real integration would replace this with
    # `Depends(get_current_student)` reading a verified session token.
    student_id: str = Field(..., description="Authenticated student ID (stand-in for a verified auth token)")
    student_email: str | None = Field(None, description="Pre-fills the email slot during Submit Grievance if provided")


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    done: bool = Field(..., description="True if this turn ended the conversation flow (ticket created, status returned, escalated, etc.)")
    escalated: bool = False
    ticket_id: str | None = None
