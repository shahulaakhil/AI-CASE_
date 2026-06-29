"""Tool 9: Bare Acts & Amendments Tracker.

Browse Indian legislation, view sections, see amendment history,
and Ask AI about any provision.

Data source: curated JSON + AI-augmented lookups.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import config
from .llm import gemini_generate

_ACTS_FILE = config.DATA_DIR / "bare_acts_data.json"

_ASK_SYSTEM = """You are a specialist in Indian legislation. A lawyer has asked you a question
about a specific provision in an Indian statute.

Rules:
1. State the exact section text first (or the closest match).
2. Explain the provision in plain, precise legal English.
3. Cite key Supreme Court / High Court interpretations of this provision.
4. Note any significant amendments and their effective dates.
5. Flag any constitutional challenges or Parliamentary Committee recommendations.
6. Do NOT speculate. If uncertain, say "the courts have not definitively settled this"."""


def _load_acts() -> list[dict]:
    if _ACTS_FILE.exists():
        try:
            return json.loads(_ACTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def list_acts() -> list[dict]:
    """Return list of available acts: [{name, year, category, description}]."""
    acts = _load_acts()
    return [{"name": a["name"], "year": a.get("year", ""), "category": a.get("category", ""), "description": a.get("description", "")} for a in acts]


def get_act_sections(act_name: str) -> list[dict]:
    """Return sections for an act: [{section, title, text, amendments}]."""
    for act in _load_acts():
        if act["name"].lower() == act_name.lower():
            return act.get("sections", [])
    return []


def search_sections(query: str) -> list[dict]:
    """Search across all acts for sections matching a keyword."""
    results = []
    for act in _load_acts():
        for sec in act.get("sections", []):
            text = f"{sec.get('title','')} {sec.get('text','')}".lower()
            if query.lower() in text:
                results.append({
                    "act": act["name"],
                    "section": sec.get("section", ""),
                    "title": sec.get("title", ""),
                    "text": sec.get("text", "")[:300],
                    "amendments": sec.get("amendments", []),
                })
    return results[:20]


def ask_provision(act_name: str, section: str, question: str) -> str:
    """Ask AI about a specific provision."""
    # Get section text if available
    section_text = ""
    for act in _load_acts():
        if act["name"].lower() == act_name.lower():
            for sec in act.get("sections", []):
                if sec.get("section", "").lower() == section.lower():
                    section_text = sec.get("text", "")
                    break

    prompt = (
        f"ACT: {act_name}\n"
        f"SECTION: {section}\n"
        f"SECTION TEXT: {section_text or '(not available in local database)'}\n\n"
        f"QUESTION: {question}"
    )
    return gemini_generate(
        prompt,
        system_instruction=_ASK_SYSTEM,
        temperature=0.15,
        max_output_tokens=2048,
    )


def get_amendments_for_act(act_name: str) -> list[dict]:
    """Return all amendments for an act."""
    for act in _load_acts():
        if act["name"].lower() == act_name.lower():
            return act.get("amendments", [])
    return []
