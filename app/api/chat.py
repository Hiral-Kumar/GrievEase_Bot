"""
The /chat endpoint — the single entrypoint a frontend chat widget calls,
tying together everything built in Steps 2-5:
  Intent routing + slot-filling (Step 4)
  -> Grievance API / DB (Step 2), Knowledge Base + RAG (Step 3),
     LLM extraction/synthesis (Step 5) as needed per turn.

One HTTP call = one conversational turn. The client is responsible for
generating (or reusing) a session_id across turns — see ChatRequest's
docstring for why session_id isn't managed via cookies here (kept explicit
and stateless-friendly for a prototype that may be called from a non-browser
client, e.g. WhatsApp/Telegram per the docs' Section 4.1 channel list).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dialogue_manager import handle_message
from app.models.chat_schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    session_id = payload.session_id or str(uuid.uuid4())

    result = handle_message(
        db, session_id, payload.message,
        student_id=payload.student_id,
        student_email=payload.student_email,
    )

    return ChatResponse(
        session_id=session_id,
        reply=result.reply,
        done=result.done,
        escalated=result.escalated,
        ticket_id=result.ticket_id,
    )
