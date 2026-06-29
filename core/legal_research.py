"""Tool 2: Legal Research Assistant.

Takes a legal question, optionally enhances the prompt, searches Indian Kanoon
(or curated corpus), and synthesises a cited answer via Gemini.
"""
from __future__ import annotations

from .llm import gemini_generate, groq_chat
from utils.kanoon import search as kanoon_search

_ROUTER_SYSTEM = """You are a query router for an Indian legal research tool.
Classify the query into one of: STATUTE, CASE_LAW, PROCEDURE, GENERAL.
Also extract: jurisdiction (High Court name / Supreme Court / District), act names, key legal concepts.
Build an optimised Indian Kanoon search query (short keyword form, not a full sentence).
Return JSON: {"intent": "...", "jurisdiction": "...", "acts": [], "concepts": [], "kanoon_query": "..."}"""

_SYNTHESIS_SYSTEM = """You are a senior advocate at the Supreme Court of India with expertise across
all branches of Indian law. Answer legal research questions with:
1. A direct answer to the question
2. Relevant statutory provisions (with section numbers)
3. Key case law (with citations — cite real, well-known Indian judgments you know with certainty)
4. Practical implications for litigation
5. Caveats / areas of legal uncertainty

Use the RETRIEVED CONTEXT for grounding where it is relevant:
- If a retrieved source is on-point, cite it as [Source N] with its case name.
- If retrieved sources are not directly relevant, answer from your legal knowledge.
  In that case, cite cases as e.g. [American Cyanamid (followed in India)] or [Balance of Convenience test — established by SC].
- NEVER invent case names, citations, or statutory text you are not certain about.
- Mark uncertain citations as [verify: description]."""


def research(question: str, max_results: int = 5) -> dict:
    """Run a legal research query. Returns {answer, sources, intent}."""
    import json

    # Step 1: classify intent and build optimised Kanoon query
    try:
        raw = groq_chat(
            [
                {"role": "system", "content": _ROUTER_SYSTEM},
                {"role": "user", "content": question},
            ],
            response_format_json=True,
            max_tokens=400,
        )
        routing = json.loads(raw)
    except Exception:
        routing = {"intent": "GENERAL", "jurisdiction": "", "acts": [], "concepts": [], "kanoon_query": question}

    # Use the router-built Kanoon query if available, else fall back to original question
    search_q = routing.get("kanoon_query") or question

    kanoon_result = kanoon_search(search_q)
    docs = kanoon_result.get("docs", [])[:max_results]
    mock_note = kanoon_result.get("_note", "")

    # Step 3: build context from search results
    context_parts = []
    for i, doc in enumerate(docs, 1):
        headline = doc.get("headline", doc.get("fragment", ""))
        title = doc.get("title", "")
        citation = doc.get("citation", "")
        cite_str = f" [{citation}]" if citation else ""
        context_parts.append(f"[Source {i}] {title}{cite_str}\n{headline}")

    context = "\n\n".join(context_parts) if context_parts else "No cases retrieved from Indian Kanoon."

    # Step 4: synthesise answer
    prompt = (
        f"RETRIEVED CONTEXT FROM INDIAN KANOON:\n{context}\n\n"
        f"LEGAL QUESTION:\n{question}\n\n"
        "Answer comprehensively. Use retrieved sources where relevant; supplement with your legal knowledge where needed."
    )

    answer = gemini_generate(
        prompt,
        system_instruction=_SYNTHESIS_SYSTEM,
        temperature=0.2,
        max_output_tokens=4096,
    )

    sources = [
        {
            "n": i + 1,
            "title": doc.get("title", ""),
            "headline": doc.get("headline", doc.get("fragment", "")),
            "tid": str(doc.get("tid", "")),
            "citation": doc.get("citation", ""),
            "date": doc.get("publishdate", ""),
        }
        for i, doc in enumerate(docs)
    ]

    return {
        "answer": answer,
        "sources": sources,
        "intent": routing.get("intent", "GENERAL"),
        "mock_note": mock_note,
    }
