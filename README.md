# GrievEase Bot 🤖

An AI-powered conversational assistant for the **GBU Grievance Management & Ticket Tracking System**, built for the GBU IT Cell Intern Recruitment Screening Challenge 2026.

**Role applied for:** AI Chatbot Development & Deployment (Experienced Intern)
**Author:** Hiral Kumar

🔗 **Live Demo:** [hiral-kumar.github.io/GrievEase_Bot](https://hiral-kumar.github.io/GrievEase_Bot/)
🔗 **Backend API (interactive docs):** [grievease-bot-api.onrender.com/docs](https://grievease-bot-api.onrender.com/docs)
🔗 **GitHub Repository:** [github.com/Hiral-Kumar/GrievEase_Bot](https://github.com/Hiral-Kumar/GrievEase_Bot)
📄 **Full Design Documentation:** [`GrievEase_Bot_Documentation.docx`](GrievEase_Bot_Documentation.docx)

> Note: the backend is deployed on Render's free tier, which spins down after inactivity. The first message may take 30-60 seconds to respond while it wakes up — this is expected.

---

## What this is

A working, tested backend for a chatbot that sits in front of the Grievance Management System and lets students:

- **Submit a grievance** through a guided conversation (not a rigid form) — category, description, and location are collected turn-by-turn, with a confirmation step before anything is saved.
- **Track a ticket's status** just by asking, using the Ticket ID.
- **Get answers to process questions** ("how long does this take?", "can I edit my grievance?") grounded in a real knowledge base — never an invented answer.
- **Get escalated to a human automatically** for harassment/safety-related reports, or after repeated failed attempts to understand a request.

It's built as six layers (see [Architecture](#architecture--how-it-maps-to-the-docs) below), each independently testable, with **73 passing tests** and **zero required external dependencies to run** — the LLM layer degrades gracefully to rule-based behavior if no API key is configured.

## Features

| Requirement (from the challenge brief) | Implementation |
|---|---|
| Student Grievance Submission | Conversational slot-filling flow with confirmation before submission |
| Auto-generated Ticket ID | `GBU-YYYY-XXXXXX` format, generated on submission |
| Track Grievance Status by Ticket ID | Natural-language status lookup |
| Admin Dashboard / Status Management | Status update API (Pending → In Progress → Resolved) |
| Email Notifications | Triggered on submission and status change |
| Responsive Design | Chat widget works on both desktop and mobile |
| Assisting with FAQs (chatbot-specific) | Retrieval-grounded knowledge base with 17 entries across 5 categories |
| Safety escalation (added innovation) | Harassment/ragging-related messages are automatically flagged and routed to a human, regardless of keyword ranking |
| Graceful LLM fallback (added innovation) | The bot remains fully functional even if the LLM API is unavailable or uncredited |


## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Chat Widget    │───▶│  /api/chat       │───▶ │  Dialogue Manager   │
│  (docs/)        │     │  (FastAPI)       │     │  (intent + slots)   │
└─────────────────┘     └──────────────────┘     └──────────┬──────────┘
                                                              │
                                    ┌─────────────────────────┼─────────────────────────┐
                                    ▼                         ▼                         ▼
                          ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
                          │  Grievance API   │     │  Knowledge Base  │     │  LLM Reasoning   │
                          │  (SQLite-backed) │     │  (TF-IDF + RAG)  │     │  (Claude API)    │
                          └──────────────────┘     └──────────────────┘     └──────────────────┘
```

| Layer | Purpose | Code |
|---|---|---|
| Chat Gateway | Single client-facing endpoint | `app/api/chat.py` |
| Dialogue Manager | Intent classification + slot-filling conversation flows | `app/core/intent_router.py`, `app/core/dialogue_manager.py` |
| Grievance API | Mock of the core ticketing system (create/track/notify) | `app/api/grievance.py`, `app/services/grievance_service.py` |
| Knowledge Base + RAG | Retrieval-grounded FAQ answers | `app/knowledge_base/`, `app/services/rag_service.py` |
| LLM Reasoning Layer | Claude API for paraphrased-complaint understanding + FAQ synthesis | `app/services/llm_client.py` |

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy (SQLite)
- **NLP / Retrieval:** scikit-learn (TF-IDF), NLTK (stemming)
- **LLM:** Anthropic Claude API
- **Frontend:** Plain HTML/CSS/JavaScript (no framework)
- **Testing:** Pytest (backend, 73 tests), Node.js + jsdom (frontend, 18 tests)
- **Deployment:** Docker + Render (backend), GitHub Pages (frontend)

  
## Quick Start

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # optional: add your ANTHROPIC_API_KEY for the LLM layer
uvicorn app.main:app --reload
```

The API is now live at `https://grievease-bot-api.onrender.com`, with interactive docs (Swagger UI) at `https://grievease-bot-api.onrender.com/docs`.

Try it immediately:
```bash
curl -X POST https://grievease-bot-api.onrender.com/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "My hostel wifi has not worked for a week", "student_id": "STU001"}'
```

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Expected: **73 passed**. No API key or network access required — the LLM-dependent tests mock the Anthropic API boundary directly (see `tests/test_llm_client.py`).

## API Reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/chat` | POST | **The one a frontend calls.** One request = one conversational turn. |
| `/api/grievance` | POST | Create a grievance directly (used internally by the chat flow; also a standalone contract per the docs) |
| `/api/grievance/{ticket_id}` | GET | Fetch status by Ticket ID |
| `/api/grievance/{ticket_id}/status` | PATCH | Admin-side status update (triggers the "Status Updated" email) |
| `/api/grievance/categories` | GET | List valid grievance categories |
| `/api/notify` | POST | Manually (re)trigger a notification email |
| `/api/kb/search` | GET | Query the knowledge base directly (`?q=...`) |

Full request/response schemas are in the interactive docs at `/docs` once the server is running.

## Key Design Decisions

**Rule-based dialogue flow, with the LLM layered on top.** Intent classification and the Submit/Track flows are handled by keyword and regex matching first, not the LLM directly. This means the two data-critical flows (submitting a grievance, tracking a ticket) are deterministic and can't be derailed by an unpredictable model response. The LLM is only consulted when the rule-based layer genuinely can't classify a message — for example, a paraphrased complaint like *"the projector in my lecture hall hasn't worked all semester"* that doesn't match any keyword. This also means the bot remains fully functional even with no API key configured or no LLM credit available — the Anthropic account behind this deployment currently has no credit balance, and the bot still handles submissions, tracking, and FAQ lookups correctly through the rule-based and retrieval paths; only the paraphrased-complaint and natural-language-FAQ-synthesis features are inactive until credit is added.

**TF-IDF instead of neural embeddings for the knowledge base.** The design docs propose sentence-transformers + a vector database for retrieval. This implementation uses scikit-learn's TF-IDF with a stemming tokenizer instead, since neural embedding models require downloading large files from Hugging Face on first use, which isn't guaranteed in every environment this might be evaluated or deployed in. At the scale of this knowledge base (a few dozen entries), TF-IDF retrieval performs comparably and is significantly easier to reason about, debug, and extend.

**A safety override on top of retrieval ranking.** Messages mentioning harassment, ragging, or abuse always surface the Harassment/Sensitive category and Escalation Policy entries first, regardless of how a plain similarity score would rank them. This was added after testing showed that a generic category (e.g. "Hostel") could technically score higher in similarity than the safety-relevant entry for a message like *"someone is harassing me in the hostel"* — since safety-critical routing shouldn't depend purely on statistical ranking, a keyword-based check enforces the right entries surface regardless.

**A question-gate to avoid false-triggering the submission flow.** A message like *"can I submit more than one grievance?"* contains the word "grievance" but is a question about the process, not a new complaint — the intent classifier specifically distinguishes statements reporting a problem from questions about the process before starting a new submission.

## How it maps to the docs

| Layer | Docs section | Code |
|---|---|---|
| Grievance Management API (mock) | Sec 8 Integration | `app/api/grievance.py`, `app/services/grievance_service.py` |
| Knowledge Base + RAG | Sec 7 KB Structure | `app/knowledge_base/`, `app/services/rag_service.py` |
| Dialogue Manager (intent + slot-filling) | Sec 5 Conversation Flow | `app/core/intent_router.py`, `app/core/dialogue_manager.py` |
| LLM Reasoning Layer | Sec 6 Prompt Design | `app/services/llm_client.py` |
| Chat Gateway | Sec 4 Architecture, Fig. 1 | `app/api/chat.py` |

## Project Structure

```
grievease-bot/
├── app/
│   ├── api/
│   │   ├── grievance.py         # Mock Grievance Management API
│   │   ├── knowledge_base.py    # KB search endpoint
│   │   └── chat.py              # POST /api/chat — the client-facing endpoint
│   ├── core/
│   │   ├── config.py, database.py
│   │   ├── intent_router.py     # Rule-based intent classification
│   │   ├── session_store.py     # Per-session conversation state
│   │   └── dialogue_manager.py  # Submit/Track slot-filling flows + LLM fallback wiring
│   ├── models/
│   │   ├── grievance.py, schemas.py    # DB model + Grievance API schemas
│   │   └── chat_schemas.py             # ChatRequest / ChatResponse
│   ├── services/
│   │   ├── grievance_service.py       # Shared create/fetch/update logic
│   │   ├── notification_service.py    # Mock/real email sending
│   │   ├── rag_service.py             # RAG context builder for the FAQ layer
│   │   └── llm_client.py              # Claude API: slot extraction + FAQ synthesis
│   ├── knowledge_base/
│   │   ├── data/kb_seed.json    # Seed KB content (source of truth)
│   │   └── retriever.py         # TF-IDF + stemming retriever, with safety override
│   └── data/                    # SQLite DB file (generated at runtime, gitignored)
├── tests/                # 73 passing tests
├── docs/                 # Chat widget frontend — named "docs" specifically so
│                         # GitHub Pages can serve it with zero config (see Deployment below)
├── docs_source/          # Documentation PDF
├── Dockerfile, .dockerignore, render.yaml   # Backend deployment
├── requirements.txt
├── .env.example
├── LICENSE
└── README.md
```

## Design notes worth reading

These document real decisions and real bugs found during development — not just the happy path.

<details>
<summary><strong>Why TF-IDF instead of sentence-transformers/Chroma for RAG</strong></summary>

The docs (Section 9) propose sentence-transformers + Chroma. This implementation uses **scikit-learn TF-IDF + cosine similarity with a stemming tokeniser** instead, deliberately:

- Sentence-transformer models download from Hugging Face on first use, needing open internet access not guaranteed in every grading/CI environment. TF-IDF needs zero downloads.
- At a few dozen KB entries, keyword-level TF-IDF performs comparably to neural embeddings and is far easier to reason about and debug.
- The retriever sits behind a stable `retrieve()` interface (`app/knowledge_base/retriever.py`), so swapping in embeddings later is a localised change, not a rewrite.

It also includes a keyword-based **safety override**: queries mentioning harassment/ragging/abuse always surface the Harassment/Sensitive and Escalation Policy entries first, regardless of raw TF-IDF ranking. This fixes a real bug found during testing — a generic "Hostel" match was outranking the safety-relevant entry for *"someone is harassing me in the hostel."*
</details>

<details>
<summary><strong>Why the Dialogue Manager is rule-based first, LLM second</strong></summary>

Intent classification and the Submit/Track flows are rule-based (keyword + regex), not LLM-driven — deliberately, so the two data-critical flows are correct and fully testable *before* any API key or network dependency enters the picture. The LLM (Step 5) layers on top as a fallback for genuinely ambiguous input, not a replacement — matching the layered design in docs Section 6.

The question-gate in `intent_router.py` specifically prevents *"can I submit more than one grievance?"* from being misread as a new complaint just because it contains the word "grievance" — only a statement reporting an actual problem starts the Submit flow.
</details>

<details>
<summary><strong>A routing bug the LLM integration surfaced (and fixed)</strong></summary>

The first version only consulted the LLM after the rule-based classifier had already decided the top-level intent was `SUBMIT_GRIEVANCE`. But a paraphrased complaint with no submit-trigger word and no keyword-matched category (e.g. *"the projector in my lecture hall hasn't worked all semester"*) gets classified as `FAQ` by elimination — so the LLM fallback was silently unreachable for exactly the case it was built for. Fixed by moving the check to the FAQ-miss path: if RAG finds no KB answer, the LLM gets one shot at recognising an unrecognised complaint before the bot gives up with "I'm not sure."
</details>

<details>
<summary><strong>A cross-test-file isolation bug (only visible when running the full suite)</strong></summary>

`test_grievance_api.py` and `test_chat_api.py` both spin up a `TestClient(app)`, and both originally pointed the app at their own SQLite file via the `DATABASE_URL` env var. That works when either file runs alone — but `app.core.config.settings` and the DB engine are process-wide singletons created on first import, so whichever test file imported first silently "won," and the other file shared that same database without either test realizing it. Fixed with FastAPI's `app.dependency_overrides` instead, which gives each file a genuinely isolated engine regardless of import order. Verified stable across multiple full-suite runs and both import orders.
</details>

## Deployment

Two pieces, deployed separately (a static frontend and a Python API don't belong on the same host):

### Backend (Render, free tier — no credit card required)
Since the API key of Claude is paid, and credits have not been added in the demo version so whenever a message that has no keyword match is sent, forcing it down the LLM path, It goes to rule-based behaviour instead of crashing.
 `https://grievease-bot-api.onrender.com`. Test it: `https://grievease-bot-api.onrender.com/docs#/chat/chat_api_chat_post` should show the Swagger UI.

Free-tier note: Render's free web services spin down after inactivity and take ~30-60 seconds to wake up on the next request — expected, not a bug, if the first demo message seems slow.

### Frontend (GitHub Pages — free, same repo)

The chat widget lives in `docs/` rather than `frontend/` specifically because GitHub Pages' "Deploy from a branch" option only offers `/ (root)` or `/docs` as folder choices — it doesn't list arbitrary folder names, so `docs/` is the path of least resistance for a zero-config Pages deploy. (The documentation PDF moved to `docs_source/` to make room.)
 Test it with the URL: `https://hiral-kumar.github.io/GrievEase_Bot/`

That's the whole deployment: two free static/container hosts, one line of config to connect them.

## Status

✅ **Backend complete** : mock Grievance API, RAG-backed Knowledge Base, Dialogue Manager, LLM Reasoning Layer, and the `/chat` endpoint — 73/73 tests passing.
✅ **Frontend complete** : chat widget (`docs/index.html`), 18/18 DOM-level tests passing.
🔜 **Deployment**: Dockerfile + `render.yaml` are ready — see [Deployment](#deployment) above for the actual click-by-click steps (requires my own GitHub/Render account, so this part is manual).

## License

MIT — see [LICENSE](LICENSE).

## Author

Hiral Kumar — Applicant, AI Chatbot Development & Deployment (Experienced Intern)
