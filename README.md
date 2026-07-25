# GrievEase Bot 🤖

An AI-powered conversational assistant for the GBU Grievance Management & Ticket Tracking System.

**Built for the GBU IT Cell Intern Recruitment — Screening Challenge 2026**
Role: AI Chatbot Development & Deployment (Experienced Intern)

> 📄 Full design documentation (architecture, conversation flow, prompt design, knowledge base structure) is in [`docs_source/GrievEase_Bot_Documentation.pdf`](docs_source/GrievEase_Bot_Documentation.pdf).

---

## What this is

A working, tested backend for a chatbot that sits in front of the Grievance Management System and lets students:

- **Submit a grievance** through a guided conversation (not a rigid form) — category, description, and location are collected turn-by-turn, with a confirmation step before anything is saved.
- **Track a ticket's status** just by asking, using the Ticket ID.
- **Get answers to process questions** ("how long does this take?", "can I edit my grievance?") grounded in a real knowledge base — never an invented answer.
- **Get escalated to a human automatically** for harassment/safety-related reports, or after repeated failed attempts to understand a request.

It's built as six layers (see [Architecture](#architecture--how-it-maps-to-the-docs) below), each independently testable, with **73 passing tests** and **zero required external dependencies to run** — the LLM layer degrades gracefully to rule-based behavior if no API key is configured.

## Quick Start

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # optional: add your ANTHROPIC_API_KEY for the LLM layer
uvicorn app.main:app --reload
```

The API is now live at `http://localhost:8000`, with interactive docs (Swagger UI) at `http://localhost:8000/docs`.

Try it immediately:
```bash
curl -X POST http://localhost:8000/api/chat \
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

## Architecture — how it maps to the docs

| Layer | Docs section | Code |
|---|---|---|
| Grievance Management API (mock) | §8 Integration | `app/api/grievance.py`, `app/services/grievance_service.py` |
| Knowledge Base + RAG | §7 KB Structure | `app/knowledge_base/`, `app/services/rag_service.py` |
| Dialogue Manager (intent + slot-filling) | §5 Conversation Flow | `app/core/intent_router.py`, `app/core/dialogue_manager.py` |
| LLM Reasoning Layer | §6 Prompt Design | `app/services/llm_client.py` |
| Chat Gateway | §4 Architecture, Fig. 1 | `app/api/chat.py` |

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
├── docs/                 # Chat widget frontend (Day 3) — named "docs" specifically so
│                         # GitHub Pages can serve it with zero config (see Deployment below)
├── docs_source/          # Day 1 documentation PDF
├── Dockerfile, .dockerignore, render.yaml   # Backend deployment (Day 3)
├── requirements.txt
├── .env.example
├── LICENSE
└── README.md
```

## Design notes worth reading

These document real decisions and real bugs found during development — not just the happy path.

<details>
<summary><strong>Why TF-IDF instead of sentence-transformers/Chroma for RAG</strong></summary>

The docs (Section 9) propose sentence-transformers + Chroma. This implementation uses **scikit-learn TF-IDF + cosine similarity with a stemming tokenizer** instead, deliberately:

- Sentence-transformer models download from Hugging Face on first use, needing open internet access not guaranteed in every grading/CI environment. TF-IDF needs zero downloads.
- At a few dozen KB entries, keyword-level TF-IDF performs comparably to neural embeddings and is far easier to reason about and debug.
- The retriever sits behind a stable `retrieve()` interface (`app/knowledge_base/retriever.py`), so swapping in embeddings later is a localized change, not a rewrite.

It also includes a keyword-based **safety override**: queries mentioning harassment/ragging/abuse always surface the Harassment/Sensitive and Escalation Policy entries first, regardless of raw TF-IDF ranking. This fixes a real bug found during testing — a generic "Hostel" match was outranking the safety-relevant entry for *"someone is harassing me in the hostel."*
</details>

<details>
<summary><strong>Why the Dialogue Manager is rule-based first, LLM second</strong></summary>

Intent classification and the Submit/Track flows are rule-based (keyword + regex), not LLM-driven — deliberately, so the two data-critical flows are correct and fully testable *before* any API key or network dependency enters the picture. The LLM (Step 5) layers on top as a fallback for genuinely ambiguous input, not a replacement — matching the layered design in docs Section 6.

The question-gate in `intent_router.py` specifically prevents *"can I submit more than one grievance?"* from being misread as a new complaint just because it contains the word "grievance" — only a statement reporting an actual problem starts the Submit flow.
</details>

<details>
<summary><strong>A routing bug the LLM integration surfaced (and fixed)</strong></summary>

The first version only consulted the LLM after the rule-based classifier had already decided the top-level intent was `SUBMIT_GRIEVANCE`. But a paraphrased complaint with no submit-trigger word and no keyword-matched category (e.g. *"the projector in my lecture hall hasn't worked all semester"*) gets classified as `FAQ` by elimination — so the LLM fallback was silently unreachable for exactly the case it was built for. Fixed by moving the check to the FAQ-miss path: if RAG finds no KB answer, the LLM gets one shot at recognizing an unrecognized complaint before the bot gives up with "I'm not sure."
</details>

<details>
<summary><strong>A cross-test-file isolation bug (only visible when running the full suite)</strong></summary>

`test_grievance_api.py` and `test_chat_api.py` both spin up a `TestClient(app)`, and both originally pointed the app at their own SQLite file via the `DATABASE_URL` env var. That works when either file runs alone — but `app.core.config.settings` and the DB engine are process-wide singletons created on first import, so whichever test file imported first silently "won," and the other file shared that same database without either test realizing it. Fixed with FastAPI's `app.dependency_overrides` instead, which gives each file a genuinely isolated engine regardless of import order. Verified stable across multiple full-suite runs and both import orders.
</details>

## Deployment

Two pieces, deployed separately (a static frontend and a Python API don't belong on the same host):

### Backend (Render, free tier — no credit card required)

1. Push this repo to GitHub (see the git history — it's already there if you're reading this from the repo).
2. Go to [render.com](https://render.com), sign in with GitHub, click **New +** → **Blueprint**.
3. Select this repo. Render reads `render.yaml` automatically and configures the service from the `Dockerfile` — no manual settings needed.
4. The one thing Render *won't* set automatically: open the new service's **Environment** tab and add `ANTHROPIC_API_KEY` with your real key (it's marked `sync: false` in `render.yaml` specifically so it's never committed to the repo). Without it, the bot still works fully via the Step 4 rule-based paths — the LLM layer just won't activate.
5. Deploy. Render gives you a URL like `https://grievease-bot-api.onrender.com`. Test it: `https://<your-url>.onrender.com/docs` should show the Swagger UI.

Free-tier note: Render's free web services spin down after inactivity and take ~30-60 seconds to wake up on the next request — expected, not a bug, if your first demo message seems slow.

### Frontend (GitHub Pages — free, same repo)

The chat widget lives in `docs/` rather than `frontend/` specifically because GitHub Pages' "Deploy from a branch" option only offers `/ (root)` or `/docs` as folder choices — it doesn't list arbitrary folder names, so `docs/` is the path of least resistance for a zero-config Pages deploy. (The Day 1 documentation PDF moved to `docs_source/` to make room.)

1. In your GitHub repo: **Settings** → **Pages** → under "Build and deployment," set Source to "Deploy from a branch," branch `main`, folder `/docs`.
2. Before it goes live, open `docs/index.html` and confirm the `API_BASE` line points at your Render URL (already done if you followed the backend step above).
3. Commit and push. GitHub gives you a URL like `https://<your-username>.github.io/GrievEase_Bot/`.

That's the whole deployment: two free static/container hosts, one line of config to connect them.

## Status

✅ **Backend complete** (Steps 1–6): mock Grievance API, RAG-backed Knowledge Base, Dialogue Manager, LLM Reasoning Layer, and the `/chat` endpoint — 73/73 tests passing.
✅ **Frontend complete** (Day 3): chat widget (`docs/index.html`), 18/18 DOM-level tests passing.
🔜 **Deployment**: Dockerfile + `render.yaml` are ready — see [Deployment](#deployment) above for the actual click-by-click steps (requires my own GitHub/Render account, so this part is manual).

## License

MIT — see [LICENSE](LICENSE).

## Author

[Your Full Name] — Applicant, AI Chatbot Development & Deployment (Experienced Intern)
