"""Tool 3: Authority Check — is a cited judgment still good law?

Strategy:
1. Extract the core case name from the citation string
2. Search Kanoon; find the best-matching TID by title similarity
3. Use citedby:{tid} to get citing cases
4. Fall back to keyword search for cases mentioning the citation text
5. Gemini analyses the citing language and classifies authority status
"""
from __future__ import annotations

import re

from .llm import gemini_json
from utils.kanoon import search as kanoon_search, citing_judgments

_STATUS_VALUES = ["GOOD LAW", "CAUTIONED", "DISTINGUISHED", "OVERRULED", "UNKNOWN"]

_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": _STATUS_VALUES},
        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "summary": {"type": "string"},
        "citing_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "case_name": {"type": "string"},
                    "treatment": {"type": "string"},
                    "excerpt": {"type": "string"},
                },
                "required": ["case_name", "treatment", "excerpt"],
            },
        },
    },
    "required": ["status", "confidence", "summary", "citing_cases"],
}

_SYSTEM = """You are a legal researcher specialising in Indian case law citation analysis.

Given a target judgment and a list of cases that cite it (or mention it), analyse how the target
judgment has been treated by subsequent Indian courts.

Treatment categories:
- GOOD LAW: Consistently followed, affirmed, or not questioned.
- CAUTIONED: Followed but with reservations; some conflicting views expressed.
- DISTINGUISHED: Frequently distinguished on facts; applied narrowly.
- OVERRULED: Expressly overruled or reversed by a superior court.
- UNKNOWN: Insufficient data to determine status.

Be conservative — mark OVERRULED only with clear evidence.
If citing cases are from an unrelated area of law, still assess based on what you find.
Return JSON matching the schema."""


def _extract_case_name(citation: str) -> str:
    """Extract party names from a full citation string."""
    # Strip citation codes like "AIR 1978 SC 597", "(2019) 5 SCC 1" etc.
    cleaned = re.sub(r'\b(AIR|SCC|SCR|Supp|SCALE|ALL|Bom|Cal|Del|Mad|Ker|MP|Raj|Guj|P&H|Ori)\b.*', '', citation, flags=re.IGNORECASE)
    cleaned = re.sub(r'\(\d{4}\).*', '', cleaned)
    return cleaned.strip().strip('.,')


def _best_matching_tid(docs: list[dict], case_name: str) -> int | None:
    """Pick the TID whose title best matches the case name (simple word overlap)."""
    if not docs:
        return None
    name_words = set(re.findall(r'\w+', case_name.lower()))
    best_score, best_tid = 0, None
    for doc in docs:
        title_words = set(re.findall(r'\w+', doc.get("title", "").lower()))
        score = len(name_words & title_words)
        if score > best_score:
            best_score = score
            best_tid = doc["tid"]
    # Only use if we got a reasonable match (at least 2 words overlap)
    return best_tid if best_score >= 2 else (docs[0]["tid"] if docs else None)


def check_authority(citation: str) -> dict:
    """Check if a judgment is still good law.

    citation: case name or citation string, e.g. "Maneka Gandhi vs Union of India AIR 1978 SC 597"
    Returns: {status, confidence, summary, citing_cases, mock_note}
    """
    mock_note = ""

    # Step 1: find the target case TID
    case_name = _extract_case_name(citation)
    case_search = kanoon_search(case_name)
    mock_note = case_search.get("_note", "")

    target_docs = case_search.get("docs", [])
    target_tid = _best_matching_tid(target_docs, case_name)

    # Step 2: get citing cases — try citedby:{tid} first, then text search fallback
    citing_docs: list[dict] = []
    if target_tid:
        cite_results = citing_judgments(target_tid)
        citing_docs = cite_results.get("docs", [])

    if not citing_docs:
        # Fallback: search for cases that mention party names from the citation
        fallback_q = case_name
        fb = kanoon_search(fallback_q)
        citing_docs = fb.get("docs", [])

    citing_docs = citing_docs[:10]

    # Step 3: build context
    context_parts = []
    for doc in citing_docs:
        title = doc.get("title", "")
        headline = doc.get("headline", doc.get("fragment", ""))
        citation_str = doc.get("citation", "")
        context_parts.append(f"{title} [{citation_str}]: {headline}")

    context = "\n\n".join(context_parts) if context_parts else "No citing cases found in Indian Kanoon."

    # Step 4: Gemini analysis
    prompt = (
        f"TARGET JUDGMENT: {citation}\n"
        f"EXTRACTED CASE NAME: {case_name}\n"
        f"TARGET TID (Indian Kanoon): {target_tid or 'not found'}\n\n"
        f"CASES FOUND IN INDIAN KANOON (citing or related):\n{context}\n\n"
        "Analyse how the target judgment has been treated by subsequent Indian courts. "
        "Also use your own legal knowledge of this landmark case if you recognise it. Return JSON."
    )

    try:
        result = gemini_json(
            prompt,
            schema=_SCHEMA,
            system_instruction=_SYSTEM,
            temperature=0.1,
            max_output_tokens=2048,
        )
    except Exception as e:
        result = {
            "status": "UNKNOWN",
            "confidence": "LOW",
            "summary": f"Analysis failed: {e}",
            "citing_cases": [],
        }

    result["mock_note"] = mock_note
    result["citation_searched"] = citation
    result["target_tid"] = target_tid
    return result
