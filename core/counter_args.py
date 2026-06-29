"""Tool 10: Counter Arguments Drafter.

1. Accepts opposing party's document (Statement of Claims / Plaint)
2. Extracts all material claims / arguments
3. Drafts a counter-argument for each claim with inline citations
4. Provides Ask AI feature for deep-dive on any claim
"""
from __future__ import annotations

from .llm import gemini_json, gemini_generate

_EXTRACT_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "claim_id": {"type": "string"},
            "claim": {"type": "string"},
            "legal_basis": {"type": "string"},
            "key_facts": {"type": "string"},
            "strength": {"type": "string", "enum": ["STRONG", "MODERATE", "WEAK"]},
        },
        "required": ["claim_id", "claim", "legal_basis", "key_facts", "strength"],
    },
}

_COUNTER_SCHEMA = {
    "type": "object",
    "properties": {
        "counter_argument": {"type": "string"},
        "legal_basis": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "relevance": {"type": "string"},
                },
                "required": ["source", "relevance"],
            },
        },
        "strategy_note": {"type": "string"},
    },
    "required": ["counter_argument", "legal_basis", "citations", "strategy_note"],
}

_EXTRACT_SYSTEM = """You are a litigation specialist. Extract each material claim,
allegation, or legal argument from the provided document.
For each claim: identify its legal basis, key supporting facts, and assess
its strength (STRONG / MODERATE / WEAK). Return JSON array."""

_COUNTER_SYSTEM = """You are a senior advocate specialising in counter-drafting for Indian litigation.

For the given claim, draft:
1. A precise counter-argument in formal legal language
2. The statutory provisions that negate or limit the claim
3. Case law that supports the counter-position (only cite real, known Indian judgments)
4. A litigation strategy note (e.g., "Challenge maintainability first")

All citations must use [CITE: <source>] format. Uncertain citations: [CITE: verify - <description>].
Do NOT hallucinate case names."""

_ASK_SYSTEM = """You are a senior litigation counsel. The lawyer has questions about
the opposing party's claim or the counter-argument strategy.

Answer based on the claim text, counter-argument, and your knowledge of Indian law.
Provide actionable litigation advice with specific legal references."""


def extract_claims(document_text: str) -> list[dict]:
    """Extract all claims from the opponent's document."""
    prompt = (
        f"Extract all material claims and legal arguments from this legal document. "
        f"Return JSON array.\n\nDOCUMENT:\n{document_text[:20000]}"
    )
    try:
        result = gemini_json(
            prompt,
            schema=_EXTRACT_SCHEMA,
            system_instruction=_EXTRACT_SYSTEM,
            temperature=0.1,
            max_output_tokens=4096,
        )
        return result if isinstance(result, list) else []
    except Exception:
        return []


def draft_counter(claim: str, legal_basis: str, context: str = "") -> dict:
    """Draft a counter-argument for a single claim."""
    prompt = (
        f"CLAIM: {claim}\n"
        f"OPPOSING LEGAL BASIS: {legal_basis}\n"
        f"{'CONTEXT: ' + context if context else ''}\n\n"
        "Draft a counter-argument with inline citations. Return JSON."
    )
    try:
        return gemini_json(
            prompt,
            schema=_COUNTER_SCHEMA,
            system_instruction=_COUNTER_SYSTEM,
            temperature=0.2,
            max_output_tokens=2048,
        )
    except Exception as e:
        return {
            "counter_argument": f"Error generating counter: {e}",
            "legal_basis": "",
            "citations": [],
            "strategy_note": "",
        }


def draft_all_counters(claims: list[dict]) -> list[dict]:
    """Draft counter-arguments for all extracted claims."""
    results = []
    for c in claims:
        counter = draft_counter(
            claim=c.get("claim", ""),
            legal_basis=c.get("legal_basis", ""),
            context=c.get("key_facts", ""),
        )
        results.append({
            "claim_id": c.get("claim_id", ""),
            "original_claim": c.get("claim", ""),
            "original_strength": c.get("strength", ""),
            **counter,
        })
    return results


def assemble_written_statement(
    petitioner: str,
    respondent: str,
    court: str,
    counters: list[dict],
    extra_defenses: str = "",
) -> str:
    """Assemble all counter-arguments into a formal Written Statement."""
    counters_text = "\n\n".join(
        f"RE CLAIM {c['claim_id']}:\n{c.get('counter_argument', '')}"
        for c in counters
    )
    prompt = (
        f"PETITIONER: {petitioner}\nRESPONDENT: {respondent}\nCOURT: {court}\n\n"
        f"COUNTER-ARGUMENTS PREPARED:\n{counters_text}\n\n"
        f"{'ADDITIONAL DEFENCES: ' + extra_defenses if extra_defenses else ''}\n\n"
        "Assemble these into a formal Written Statement under Order VIII CPC with: "
        "cause title, preliminary objections, para-wise reply with inline citations, "
        "positive case for defendant, and prayer."
    )
    return gemini_generate(
        prompt,
        temperature=0.25,
        max_output_tokens=8192,
    )


def ask_about_claim(question: str, claim: str, counter: str = "") -> str:
    """Ask AI about a specific claim or counter-argument."""
    prompt = (
        f"CLAIM FROM OPPOSING PARTY:\n{claim}\n\n"
        f"{'COUNTER-ARGUMENT DRAFTED:\n' + counter + chr(10) + chr(10) if counter else ''}"
        f"LAWYER'S QUESTION: {question}"
    )
    return gemini_generate(
        prompt,
        system_instruction=_ASK_SYSTEM,
        temperature=0.15,
        max_output_tokens=2048,
    )
