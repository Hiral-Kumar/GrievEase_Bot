"""
RAG service — sits between the raw KnowledgeBaseRetriever and the LLM layer
(added in Step 5). Its job is to decide *whether* we have enough grounding
to answer at all, and to format that grounding consistently for the prompt
template described in Day 1 docs, Section 6.2.
"""
from dataclasses import dataclass

from app.knowledge_base.retriever import get_retriever, KBChunk


@dataclass
class RAGResult:
    has_answer: bool
    context_text: str
    sources: list[KBChunk]


def build_rag_context(query: str, top_k: int = 3) -> RAGResult:
    """
    Retrieves relevant KB chunks for a query and formats them as a single
    context block ready to inject into the FAQ/RAG prompt template.

    If nothing sufficiently relevant is found, `has_answer` is False — the
    dialogue manager / LLM layer should use this to trigger the "I'm not
    sure, would you like me to connect you with a staff member?" fallback
    instead of letting the LLM guess.
    """
    retriever = get_retriever()
    chunks = retriever.retrieve(query, top_k=top_k)

    if not chunks:
        return RAGResult(has_answer=False, context_text="", sources=[])

    context_lines = [
        f"[{c.topic}] {c.content}" for c in chunks
    ]
    context_text = "\n".join(context_lines)
    return RAGResult(has_answer=True, context_text=context_text, sources=chunks)
