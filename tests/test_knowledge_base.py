"""
Tests for Step 3 — Knowledge Base retrieval and the RAG service layer.

These specifically pin down two real bugs found and fixed during development:
  1. Off-topic queries must return no match (score+overlap guard).
  2. Safety-critical queries (harassment/ragging) must always surface the
     Harassment/Sensitive + Escalation Policy entries, since a generic
     category (e.g. "Hostel") can otherwise outrank them on pure TF-IDF.

Run with: pytest tests/test_knowledge_base.py -v
"""
from app.knowledge_base.retriever import KnowledgeBaseRetriever
from app.services.rag_service import build_rag_context


def test_relevant_query_returns_expected_topic():
    r = KnowledgeBaseRetriever()
    results = r.retrieve("How long will it take to resolve my complaint?")
    assert results, "expected at least one match for a clearly relevant query"
    assert results[0].topic == "Resolution time"


def test_offtopic_query_returns_no_match():
    r = KnowledgeBaseRetriever()
    assert r.retrieve("What is the weather like today?") == []
    assert r.retrieve("who won the cricket match") == []


def test_harassment_query_surfaces_safety_entries_first():
    r = KnowledgeBaseRetriever()
    results = r.retrieve("someone is harassing me in the hostel")
    topics = [c.topic for c in results]
    assert "Harassment / Sensitive" in topics
    # Must be ranked ahead of the generic Hostel category despite lower raw score.
    assert topics.index("Harassment / Sensitive") < topics.index("Hostel")


def test_ragging_query_triggers_safety_override():
    r = KnowledgeBaseRetriever()
    results = r.retrieve("I want to report ragging by a senior student")
    assert results[0].topic == "Harassment / Sensitive"


def test_wifi_query_matches_hostel_and_sample_case():
    r = KnowledgeBaseRetriever()
    results = r.retrieve("my wifi in the hostel is not working")
    topics = {c.topic for c in results}
    assert "Hostel" in topics or "Hostel Wi-Fi outage (anonymized example)" in topics


def test_rag_service_no_answer_for_offtopic():
    result = build_rag_context("What is the weather like today?")
    assert result.has_answer is False
    assert result.context_text == ""
    assert result.sources == []


def test_rag_service_has_answer_for_relevant_query():
    result = build_rag_context("can I edit my grievance after I submit it")
    assert result.has_answer is True
    assert "Editing or withdrawing a grievance" in result.context_text
    assert len(result.sources) >= 1
