"""
Knowledge Base inspection endpoint — lets an admin (or the chatbot's own
debugging/testing) query the KB directly, independent of the full chat flow.
Not part of the mandatory challenge features, but a small, useful addition
for verifying RAG retrieval quality and for future KB-content review tooling.
"""
from fastapi import APIRouter, Query
from app.services.rag_service import build_rag_context

router = APIRouter(prefix="/api/kb", tags=["knowledge_base"])


@router.get("/search")
def search_knowledge_base(q: str = Query(..., min_length=3), top_k: int = 3):
    """Returns the top matching KB chunks for a query, with relevance scores."""
    result = build_rag_context(q, top_k=top_k)
    return {
        "query": q,
        "has_answer": result.has_answer,
        "sources": [
            {"id": s.id, "topic": s.topic, "category": s.category, "score": round(s.score, 3)}
            for s in result.sources
        ],
    }
