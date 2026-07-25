"""
GrievEase Bot — application entrypoint.

Wires up all three API surfaces built across Steps 2-6:
  - Mock Grievance Management API   (app/api/grievance.py,     Step 2)
  - Knowledge Base search           (app/api/knowledge_base.py, Step 3)
  - Chat endpoint                   (app/api/chat.py,           Step 6)

The chat endpoint is the one a real frontend widget calls; the other two
exist independently for direct testing/inspection and because the docs'
architecture (Section 8) treats the Grievance API as a contract the chatbot
integrates with, not something private to it.
"""
from fastapi import FastAPI
from app.core.database import init_db
from app.api import grievance, knowledge_base, chat

app = FastAPI(
    title="GrievEase Bot API",
    description="AI-powered conversational assistant for the GBU Grievance Management & Ticket Tracking System.",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "service": "GrievEase Bot API"}


app.include_router(grievance.router)
app.include_router(knowledge_base.router)
app.include_router(chat.router)
