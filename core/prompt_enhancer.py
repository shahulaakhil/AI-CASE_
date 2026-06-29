"""Tool 5: Prompt Enhancement.

Lawyers think in facts, disputes, and outcomes.
LLMs perform best with structured, layered prompts.
This tool bridges the gap by transforming a raw lawyer query into
an optimised LLM instruction set.
"""
from __future__ import annotations

from .llm import gemini_generate

_SYSTEM = """You are a prompt engineering expert specialising in legal AI applications for India.

A lawyer has given you a raw, natural-language legal query. Your job is to transform it
into a well-structured, high-quality LLM prompt that will produce optimal legal research results.

Your enhanced prompt MUST include:
1. CONTEXT: What is the legal situation / jurisdiction / applicable law domain?
2. SPECIFIC QUESTIONS: Break the question into 3-5 precise sub-questions
3. DESIRED OUTPUT FORMAT: Specify what kind of answer is needed
   (e.g., case law + statute + practical advice, or just case law, etc.)
4. CONSTRAINTS: Any limitations (e.g., "only Supreme Court judgments post-2010")
5. OUTPUT STYLE: Academic legal memo style / court-ready / plain language

Output the enhanced prompt in a clean, copy-ready format.
Also include a one-line "Enhancement note" explaining what you changed and why."""

_CLASSIFY_SYSTEM = """Classify the legal query into one or more of:
CONSTITUTIONAL, CONTRACT, TORT, CRIMINAL, FAMILY, PROPERTY, IPR,
CONSUMER, LABOUR, TAX, CORPORATE, PROCEDURE, EVIDENCE, OTHER.
Return JSON: {"categories": [...], "jurisdiction": "Supreme Court / High Court / District Court / Tribunal"}"""


def enhance_prompt(raw_query: str) -> dict:
    """Transform a raw lawyer query into an optimised LLM prompt.

    Returns: {enhanced_prompt, enhancement_note, categories, jurisdiction}
    """
    import json

    # Classify the query
    try:
        raw = gemini_generate(
            raw_query,
            system_instruction=_CLASSIFY_SYSTEM,
            response_mime_type="application/json",
            max_output_tokens=200,
            temperature=0.0,
        )
        classification = json.loads(raw)
    except Exception:
        classification = {"categories": ["OTHER"], "jurisdiction": "Supreme Court"}

    # Enhance the prompt
    category_hint = ", ".join(classification.get("categories", []))
    prompt = (
        f"RAW LAWYER QUERY: {raw_query}\n\n"
        f"DETECTED LEGAL AREA: {category_hint}\n"
        f"JURISDICTION CONTEXT: {classification.get('jurisdiction', 'Indian courts')}\n\n"
        "Transform this into an optimised LLM prompt for legal research. "
        "End with 'Enhancement note: [one line explaining what you changed]'"
    )

    enhanced = gemini_generate(
        prompt,
        system_instruction=_SYSTEM,
        temperature=0.3,
        max_output_tokens=1500,
    )

    # Split enhancement note
    note = ""
    lines = enhanced.strip().splitlines()
    for i, line in enumerate(lines):
        if line.lower().startswith("enhancement note"):
            note = line.split(":", 1)[-1].strip()
            enhanced = "\n".join(lines[:i]).strip()
            break

    return {
        "enhanced_prompt": enhanced,
        "enhancement_note": note,
        "categories": classification.get("categories", []),
        "jurisdiction": classification.get("jurisdiction", ""),
    }
