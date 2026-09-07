"""Bare Acts browser, section search and provision question answering."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .. import settings
from ..llm import registry as llm

_ASK_SYSTEM = """You are a specialist in Indian legislation advising a practising advocate on a
specific statutory provision.

Answer in this order:
1. The text of the provision, quoted where it is supplied to you, or the closest accurate
   statement of it where it is not.
2. What it means, in precise plain legal English.
3. How the courts have read it, naming the leading Supreme Court and High Court authorities
   you are confident about, with citations.
4. Amendments that changed it, with the amending Act and the date it took effect.
5. Any constitutional challenge, referral to a larger bench, or pending question.

Rules:
Never invent a citation, a section number or statutory text.
Where the position is unsettled, say that the courts have not settled it and explain the
competing views.
Where the local database text is missing, say that you are answering from general knowledge
of the statute and that the exact wording should be checked against the bare act."""


@lru_cache(maxsize=1)
def _acts() -> list[dict]:
    path = settings.BARE_ACTS_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def reload_acts() -> None:
    _acts.cache_clear()


def _act_summary(act: dict) -> dict:
    sections = act.get("sections") or []
    amended = sum(1 for section in sections if section.get("amendments"))
    return {
        "name": act.get("name", ""),
        "year": str(act.get("year", "")),
        "category": act.get("category", "Other"),
        "description": act.get("description", ""),
        "section_count": len(sections),
        "amended_section_count": amended,
        "amendment_count": len(act.get("amendments") or []),
    }


def list_acts() -> list[dict]:
    return [_act_summary(act) for act in _acts()]


def categories() -> list[str]:
    return sorted({act.get("category", "Other") for act in _acts()})


def find_act(name: str) -> dict | None:
    target = (name or "").strip().lower()
    for act in _acts():
        if act.get("name", "").strip().lower() == target:
            return act
    return None


def act_detail(name: str) -> dict | None:
    act = find_act(name)
    if act is None:
        return None
    detail = _act_summary(act)
    detail["sections"] = [
        {
            "section": section.get("section", ""),
            "title": section.get("title", ""),
            "text": section.get("text", ""),
            "amendments": section.get("amendments") or [],
        }
        for section in act.get("sections") or []
    ]
    detail["amendments"] = act.get("amendments") or []
    return detail


def search_sections(query: str, limit: int = 40) -> list[dict]:
    needle = (query or "").strip().lower()
    if len(needle) < 2:
        return []
    pattern = re.compile(re.escape(needle), re.IGNORECASE)

    results: list[dict] = []
    for act in _acts():
        for section in act.get("sections") or []:
            title = section.get("title", "")
            text = section.get("text", "")
            number = section.get("section", "")
            haystack = f"{number} {title} {text}".lower()
            if needle not in haystack:
                continue

            match = pattern.search(text)
            if match:
                start = max(0, match.start() - 90)
                snippet = text[start : match.end() + 170].strip()
                if start > 0:
                    snippet = "..." + snippet
            else:
                snippet = text[:240]

            score = 0
            if needle in number.lower():
                score += 3
            if needle in title.lower():
                score += 2
            results.append(
                {
                    "act": act.get("name", ""),
                    "category": act.get("category", "Other"),
                    "section": number,
                    "title": title,
                    "snippet": snippet,
                    "text": text,
                    "amendments": section.get("amendments") or [],
                    "_score": score,
                }
            )

    results.sort(key=lambda item: item["_score"], reverse=True)
    for item in results:
        item.pop("_score", None)
    return results[:limit]


def section_text(act_name: str, section_number: str) -> tuple[str, str]:
    act = find_act(act_name)
    if act is None:
        return "", ""
    target = (section_number or "").strip().lower()
    for section in act.get("sections") or []:
        if section.get("section", "").strip().lower() == target:
            return section.get("text", ""), section.get("title", "")
    return "", ""


def amendments_for_act(act_name: str) -> list[dict]:
    act = find_act(act_name)
    return (act.get("amendments") or []) if act else []


def ask_provision(
    act_name: str,
    section_number: str,
    question: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    text, title = section_text(act_name, section_number)
    act = find_act(act_name)
    amendments: list[dict] = []
    if act:
        for section in act.get("sections") or []:
            if section.get("section", "").strip().lower() == (section_number or "").strip().lower():
                amendments = section.get("amendments") or []
                break

    amendment_block = ""
    if amendments:
        amendment_block = "\nRECORDED AMENDMENTS:\n" + "\n".join(
            f"{item.get('year', '')}: {item.get('description', '')} "
            f"({item.get('amending_act', '')})"
            for item in amendments
        )

    prompt = (
        f"ACT: {act_name}\n"
        f"SECTION: {section_number or 'the Act generally'}\n"
        f"SECTION HEADING: {title or 'not recorded'}\n"
        f"SECTION TEXT FROM THE LOCAL DATABASE:\n"
        f"{text or 'not available in the local database'}\n"
        f"{amendment_block}\n\n"
        f"QUESTION FROM THE ADVOCATE: {question}"
    )
    answer = llm.generate(
        prompt,
        provider=provider,
        model=model,
        system=_ASK_SYSTEM,
        temperature=0.15,
        max_tokens=3500,
    )
    return {
        "answer": answer,
        "act": act_name,
        "section": section_number,
        "section_title": title,
        "section_text": text,
        "amendments": amendments,
    }


def stats() -> dict[str, Any]:
    acts = _acts()
    sections = sum(len(act.get("sections") or []) for act in acts)
    amendments = sum(len(act.get("amendments") or []) for act in acts)
    amendments += sum(
        len(section.get("amendments") or [])
        for act in acts
        for section in act.get("sections") or []
    )
    return {"acts": len(acts), "sections": sections, "amendments": amendments}
