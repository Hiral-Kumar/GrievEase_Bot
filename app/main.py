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
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import init_db
from app.api import grievance, knowledge_base, chat

app = FastAPI(
    title="GrievEase Bot API",
    description="AI-powered conversational assistant for the GBU Grievance Management & Ticket Tracking System.",
    version="1.0.0",
)

# CORS: the frontend/ widget (Day 3) is a static HTML file that may be opened
# directly, served from a different origin (e.g. GitHub Pages or a local
# static server), or embedded in the student portal on a different domain
# than this API — all of which trigger the browser's CORS check on the
# /api/chat fetch() call. Wide open (allow_origins=["*"]) is fine here since
# every endpoint is either read-only (categories, KB search) or scoped to
# whatever student_id the caller supplies — there's no cookie/session-based
# auth for CORS to protect in this prototype. A real deployment sitting
# behind the actual GBU student portal's auth would restrict this to that
# portal's exact origin instead.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
