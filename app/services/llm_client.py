"""
LLM Reasoning Layer — the "LLM Reasoning Layer" box from the architecture
diagram (Day 1 docs, Fig. 1), implementing the prompt design from Section 6.

This layer does two jobs, both used as an *enhancement* on top of the
rule-based Dialogue Manager (Step 4), never as a replacement for it:

  1. Slot extraction — when a free-text message doesn't match any keyword in
     `intent_router.classify_category`, ask Claude to extract a category +
     structured description instead of immediately asking the student to
     pick from a menu. This is the "paraphrased complaint" case the docs
     call out (Section 2): a student describing a problem in their own
     words shouldn't be forced into rigid phrasing.
  2. FAQ answer synthesis — turn 1-3 raw KB chunks (Step 3) into a natural,
     conversational answer grounded only in that retrieved context, per the
     FAQ/RAG prompt template in Section 6.2.

Design choice: every function here degrades gracefully to `None` if no API
key is configured, or if the call fails for any reason (network, rate limit,
malformed response). The Dialogue Manager already has a correct, fully
rule-based fallback for both cases (ask the category menu; return the raw
top KB chunk) — so an LLM outage should degrade the experience, not break
it. This mirrors the confidence-based router described in the docs
(Section 3.1): the LLM augments the deterministic flows, it doesn't gate them.
"""
import json
import logging
from dataclasses import dataclass

from app.core.config import settings
from app.models.grievance import GrievanceCategory

logger = logging.getLogger("grievease.llm")

SYSTEM_PROMPT = """You are GrievEase Bot, GBU's grievance assistant.

Capabilities: you help students submit grievances, check status by Ticket ID, \
and answer FAQs about the grievance process.

Guardrails:
- Never invent a ticket status, resolution time, or policy detail. Only use \
information explicitly given to you in this prompt's context.
- If you don't have enough grounding to answer, say so plainly rather than \
guessing.
- Keep responses concise: under 4 sentences unless you are summarizing a \
grievance submission for confirmation.
- Never ask for information unrelated to the grievance process (e.g. \
passwords, payment details).
"""

_client = None
_client_init_attempted = False


def _get_client():
    """
    Lazily constructs the Anthropic client. Returns None (rather than
    raising) if no API key is configured, so every caller can treat "no LLM
    available" as a normal, expected state instead of a crash.
    """
    global _client, _client_init_attempted
    if _client_init_attempted:
        return _client
    _client_init_attempted = True

    if not settings.ANTHROPIC_API_KEY:
        logger.info("ANTHROPIC_API_KEY not set — LLM layer disabled, rule-based fallbacks will be used.")
        return None

    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    except Exception:
        logger.exception("Failed to initialize Anthropic client — LLM layer disabled.")
        _client = None
    return _client


def _call_claude(user_prompt: str, max_tokens: int = 400) -> str | None:
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()
    except Exception:
        logger.exception("Claude API call failed — falling back to rule-based path.")
        return None


# ---------------------------------------------------------------------------
# 1. Slot extraction
# ---------------------------------------------------------------------------

@dataclass
class ExtractedSlots:
    category: GrievanceCategory | None
    description: str | None


_CATEGORY_VALUES = [c.value for c in GrievanceCategory]

_SLOT_EXTRACTION_TEMPLATE = """A student sent this message to a grievance chatbot:

"{message}"

Classify it into exactly one of these categories: {categories}

Respond with ONLY a JSON object (no other text, no markdown fences) in this \
exact shape:
{{"category": "<one of the categories above, or null if genuinely none fit>", \
"description": "<a clean one-sentence restatement of the student's issue, or \
null if the message isn't describing a problem at all>"}}
"""


def extract_slots(message: str) -> ExtractedSlots | None:
    """
    Asks Claude to classify a free-text message into a category + clean
    description. Returns None if the LLM is unavailable or the response
    can't be parsed as valid JSON with a recognized category — the caller
    (dialogue_manager) treats None exactly like "rule-based match also
    failed" and falls back to asking the student to pick from the menu.
    """
    prompt = _SLOT_EXTRACTION_TEMPLATE.format(
        message=message.replace('"', "'"),
        categories=", ".join(_CATEGORY_VALUES),
    )
    raw = _call_claude(prompt, max_tokens=200)
    if raw is None:
        return None

    try:
        # Defensive: strip markdown fences if the model added them anyway.
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Slot extraction returned non-JSON output: %r", raw)
        return None

    category_str = data.get("category")
    category = None
    if category_str:
        try:
            category = GrievanceCategory(category_str)
        except ValueError:
            logger.warning("Slot extraction returned an unrecognized category: %r", category_str)
            return None

    description = data.get("description") or None
    if category is None or description is None:
        return None
    return ExtractedSlots(category=category, description=description)


# ---------------------------------------------------------------------------
# 2. FAQ answer synthesis (Section 6.2 — FAQ/RAG prompt template)
# ---------------------------------------------------------------------------

_FAQ_PROMPT_TEMPLATE = """Using only the context below, answer the student's \
question in 2-3 sentences. If the answer genuinely isn't in the context, say \
you're not sure and suggest connecting them with staff — do not use outside \
knowledge.

Context:
{context}

Question: {question}
"""


def synthesize_faq_answer(question: str, context_text: str) -> str | None:
    """
    Turns retrieved KB chunks into a natural answer grounded strictly in
    that context. Returns None if the LLM is unavailable or errors, so the
    caller falls back to returning the raw top KB chunk verbatim — a
    correct, if less polished, answer.
    """
    prompt = _FAQ_PROMPT_TEMPLATE.format(context=context_text, question=question)
    return _call_claude(prompt, max_tokens=250)
