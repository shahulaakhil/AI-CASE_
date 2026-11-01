"""List of Dates, Judgment Summariser and Authority Check."""
from __future__ import annotations

import re
from typing import Any

from ..llm import registry as llm
from . import kanoon
from .documents import clip

# ---------------------------------------------------------------------------
# Tool 1: List of Dates
# ---------------------------------------------------------------------------

_DATES_SYSTEM = """You are a senior litigation paralegal in an Indian law firm.

Extract every material date and the corresponding event from the document supplied.
Be exhaustive. A missed date can lose a limitation point.

Rules:
1. Only record dates that actually appear in the text. Never invent a date.
2. Normalise every date to DD-MM-YYYY where the full date is known. If only a month
   and year appear, write it as "MM-YYYY (approximate)". If the text says something
   like "sometime in January 2022", record "01-2022 (approximate)".
3. Describe the event in precise legal language, at most 25 words.
4. The source field names the paragraph, clause, page or heading where the date appears.
5. The significance field is one short line of legal consequence, for example
   "Date of cause of action", "Filing of FIR", "Limitation starts to run".
6. Sort the array in chronological order.
7. Put every date you find in one single array. Never stop after the first entry."""

_DATES_SHAPE = """{"items": [
  {"date": "12-03-2021", "event": "...", "source": "Para 4 of the plaint", "significance": "..."}
]}"""


def _as_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("dates", "events", "rows", "items", "list_of_dates", "result", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
        else:
            rows = []
    else:
        rows = []

    cleaned: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cleaned.append(
            {
                "date": str(row.get("date", "")).strip(),
                "event": str(row.get("event", "")).strip(),
                "source": str(row.get("source", "")).strip(),
                "significance": str(row.get("significance", "")).strip(),
            }
        )
    return [row for row in cleaned if row["date"] or row["event"]]


def list_of_dates(
    text: str, *, case_title: str = "", provider: str | None = None, model: str | None = None
) -> list[dict]:
    header = f"CASE: {case_title}\n\n" if case_title else ""
    prompt = (
        f"{header}Extract every material date and event from the legal document below, "
        f"sorted chronologically.\n\nDOCUMENT:\n{clip(text, 60000)}"
    )
    payload = llm.generate_json(
        prompt,
        provider=provider,
        model=model,
        system=_DATES_SYSTEM,
        schema_hint=_DATES_SHAPE,
        temperature=0.1,
        max_tokens=6000,
        expect_list=True,
    )
    return _as_rows(payload)


# ---------------------------------------------------------------------------
# Tool 8: Judgment Summariser
# ---------------------------------------------------------------------------

_BRIEF_SYSTEM = """You are a senior judicial research clerk preparing an 8-card structured brief for an Indian litigation workbench.

Rules:
1. Work strictly from the judgment supplied. Never add facts not in the text.
2. Populate all 8 structured modules:
   - case_summary: case_name, citation, court, year, case_type, key_facts, issue.
   - key_legal_provisions: list of {provision, description}.
   - key_issue: the single primary legal question framed.
   - timeline_of_events: list of {year_or_date, event}.
   - findings_and_reasoning: list of 3-6 key legal principles or reasons.
   - outcome: operative final ruling and holding.
   - source_references: list of primary legal citations and sources.
   - groundedness_reliability: list of {claim, source} mapping key findings to page/para.
3. Return valid JSON only."""

_BRIEF_SHAPE = """{
  "case_details": {"case_name": "", "citation": "", "court": "", "bench": "", "date_of_judgment": "", "year": "", "case_type": "", "subject_matter": ""},
  "case_summary": {"case_name": "", "citation": "", "court": "", "year": "", "case_type": "", "key_facts": "", "issue": ""},
  "key_legal_provisions": [{"provision": "", "description": ""}], 
  "key_issue": "",
  "timeline_of_events": [{"year_or_date": "", "event": ""}], 
  "findings_and_reasoning": [""],
  "outcome": "",
  "source_references": [""],
  "groundedness_reliability": [{"claim": "", "source": ""}], 
  "facts": "",
  "issues": [""],
  "petitioner_arguments": "",
  "respondent_arguments": "",
  "held": "",
  "ratio": "",
  "significance": "",
  "key_statutes_cited": [""],
  "key_cases_cited": [""]
}"""

_EMPTY_BRIEF = {
    "case_details": {
        "case_name": "", "citation": "", "court": "", "bench": "", "date_of_judgment": "", "year": "", "case_type": "", "subject_matter": ""
    },
    "case_summary": {
        "case_name": "", "citation": "", "court": "", "year": "", "case_type": "", "key_facts": "", "issue": ""
    },
    "key_legal_provisions": [],
    "key_issue": "",
    "timeline_of_events": [],
    "findings_and_reasoning": [],
    "outcome": "",
    "source_references": [],
    "groundedness_reliability": [],
    "facts": "",
    "issues": [],
    "petitioner_arguments": "",
    "respondent_arguments": "",
    "held": "",
    "ratio": "",
    "significance": "",
    "key_statutes_cited": [],
    "key_cases_cited": [],
}


def _normalise_brief(payload: Any) -> dict:
    brief = dict(_EMPTY_BRIEF)
    brief["case_details"] = dict(_EMPTY_BRIEF["case_details"])
    brief["case_summary"] = dict(_EMPTY_BRIEF["case_summary"])
    if not isinstance(payload, dict):
        return brief

    details = payload.get("case_details") or {}
    if isinstance(details, dict):
        for key in brief["case_details"]:
            brief["case_details"][key] = str(details.get(key, "") or "").strip()

    for key in ("facts", "petitioner_arguments", "respondent_arguments", "held", "ratio", "significance", "key_issue", "outcome"):
        value = payload.get(key, "")
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value)
        brief[key] = str(value or "").strip()

    for key in ("issues", "key_statutes_cited", "key_cases_cited", "findings_and_reasoning", "source_references"):
        value = payload.get(key) or []
        if isinstance(value, str):
            value = [line.strip("-* ") for line in value.split("\n") if line.strip()]
        brief[key] = [str(item).strip() for item in value if str(item).strip()]

    cs = payload.get("case_summary") or {}
    if not isinstance(cs, dict):
        cs = {}
    brief["case_summary"] = {
        "case_name": str(cs.get("case_name") or brief["case_details"].get("case_name") or "").strip(),
        "citation": str(cs.get("citation") or brief["case_details"].get("citation") or "").strip(),
        "court": str(cs.get("court") or brief["case_details"].get("court") or "").strip(),
        "year": str(cs.get("year") or brief["case_details"].get("year") or (brief["case_details"].get("date_of_judgment", "")[-4:]) or "").strip(),
        "case_type": str(cs.get("case_type") or brief["case_details"].get("case_type") or brief["case_details"].get("subject_matter") or "").strip(),
        "key_facts": str(cs.get("key_facts") or brief.get("facts") or "").strip(),
        "issue": str(cs.get("issue") or brief.get("key_issue") or (brief["issues"][0] if brief["issues"] else "")).strip(),
    }

    if not brief["key_issue"]:
        brief["key_issue"] = brief["case_summary"]["issue"] or (brief["issues"][0] if brief["issues"] else "")
    if not brief["outcome"]:
        brief["outcome"] = brief.get("held") or ""

    klp = payload.get("key_legal_provisions") or []
    if isinstance(klp, list):
        clean_klp = []
        for item in klp:
            if isinstance(item, dict):
                p = str(item.get("provision") or item.get("article") or item.get("section") or "").strip()
                d = str(item.get("description") or item.get("principle") or "").strip()
                if p:
                    clean_klp.append({"provision": p, "description": d})
            elif isinstance(item, str) and item.strip():
                clean_klp.append({"provision": item.strip(), "description": ""})
        brief["key_legal_provisions"] = clean_klp
    if not brief["key_legal_provisions"] and brief["key_statutes_cited"]:
        brief["key_legal_provisions"] = [{"provision": s, "description": ""} for s in brief["key_statutes_cited"]]

    toe = payload.get("timeline_of_events") or []
    if isinstance(toe, list):
        clean_toe = []
        for item in toe:
            if isinstance(item, dict):
                y = str(item.get("year_or_date") or item.get("date") or item.get("year") or "").strip()
                e = str(item.get("event") or item.get("description") or "").strip()
                if y or e:
                    clean_toe.append({"year_or_date": y, "event": e})
            elif isinstance(item, str) and item.strip():
                clean_toe.append({"year_or_date": "", "event": item.strip()})
        brief["timeline_of_events"] = clean_toe

    if not brief["findings_and_reasoning"]:
        if brief.get("ratio"):
            brief["findings_and_reasoning"].append(brief["ratio"])
        if brief.get("significance"):
            brief["findings_and_reasoning"].append(brief["significance"])

    if not brief["source_references"]:
        c = brief["case_details"].get("citation")
        if c:
            brief["source_references"].append(c)
        for cs_item in brief["key_cases_cited"][:3]:
            brief["source_references"].append(cs_item)

    gr = payload.get("groundedness_reliability") or []
    if isinstance(gr, list):
        clean_gr = []
        for item in gr:
            if isinstance(item, dict):
                cl = str(item.get("claim") or item.get("element") or "").strip()
                sc = str(item.get("source") or item.get("page_para") or item.get("reference") or "").strip()
                if cl or sc:
                    clean_gr.append({"claim": cl, "source": sc})
        brief["groundedness_reliability"] = clean_gr

    return brief


def summarise_judgment(
    text: str, *, provider: str | None = None, model: str | None = None
) -> dict:
    prompt = (
        "Summarise the judgment below into a structured brief. Return JSON only.\n\n"
        f"JUDGMENT TEXT:\n{clip(text, 70000)}"
    )
    payload = llm.generate_json(
        prompt,
        provider=provider,
        model=model,
        system=_BRIEF_SYSTEM,
        schema_hint=_BRIEF_SHAPE,
        temperature=0.1,
        max_tokens=7000,
    )
    return _normalise_brief(payload)


# ---------------------------------------------------------------------------
# Tool 3: Authority Check
# ---------------------------------------------------------------------------

STATUS_VALUES = ("GOOD LAW", "CAUTIONED", "DISTINGUISHED", "OVERRULED", "UNKNOWN")

_AUTHORITY_SYSTEM = """You analyse how Indian courts have treated a cited judgment.

Treatment categories:
GOOD LAW      The judgment is consistently followed or affirmed and has not been doubted.
CAUTIONED     It is followed but with reservations, or conflicting views exist.
DISTINGUISHED It is frequently distinguished on facts and applied narrowly.
OVERRULED     It has been expressly overruled or reversed by a larger or superior bench.
UNKNOWN       There is not enough material to reach a view.

Rules:
1. Be conservative. Return OVERRULED only where the material clearly shows it.
2. Use the retrieved citing cases as the primary evidence.
3. You may also rely on your own knowledge of landmark Indian judgments, but say so in
   the summary when you do.
4. Never invent a case name or a citation. If unsure, leave citing_cases empty.
5. The summary must be three to six sentences a litigator can act on."""

_AUTHORITY_SHAPE = """{
  "status": "GOOD LAW | CAUTIONED | DISTINGUISHED | OVERRULED | UNKNOWN",
  "confidence": "HIGH | MEDIUM | LOW",
  "summary": "",
  "citing_cases": [{"case_name": "", "treatment": "", "excerpt": ""}]
}"""

_CITATION_CODES = (
    r"AIR|SCC|SCR|SCALE|Supp|ALL|Bom|Cal|Del|Mad|Ker|Kar|MP|Raj|Guj|P&H|Ori|Pat|Jhar|"
    r"Gau|Sikk|Tri|HP|J&K|Utt|Chh|Telangana|AP"
)


def _core_case_name(citation: str) -> str:
    cleaned = re.sub(rf"\b({_CITATION_CODES})\b.*", "", citation, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(\s*\d{4}\s*\).*", "", cleaned)
    cleaned = re.sub(r"\b\d{4}\b.*", "", cleaned)
    cleaned = cleaned.strip().strip(".,;:")
    return cleaned or citation.strip()


def _best_tid(docs: list[dict], case_name: str) -> str | None:
    if not docs:
        return None
    wanted = set(re.findall(r"\w+", case_name.lower())) - {"vs", "v", "versus", "and", "the", "of"}
    best_score, best_tid = 0, None
    for doc in docs:
        title_words = set(re.findall(r"\w+", doc.get("title", "").lower()))
        score = len(wanted & title_words)
        if score > best_score:
            best_score, best_tid = score, doc.get("tid")
    if best_score >= 2:
        return best_tid
    return docs[0].get("tid")


def check_authority(
    citation: str, *, provider: str | None = None, model: str | None = None
) -> dict:
    case_name = _core_case_name(citation)
    target = kanoon.search(case_name)
    note = target.get("note", "")

    target_tid = _best_tid(target.get("docs", []), case_name)
    citing_docs: list[dict] = []
    if target_tid and kanoon.configured():
        citing_docs = kanoon.citing_judgments(target_tid).get("docs", [])
    if not citing_docs:
        citing_docs = target.get("docs", [])
    citing_docs = citing_docs[:10]

    if citing_docs:
        context = "\n\n".join(
            f"{doc.get('title', '')} [{doc.get('citation', '')}] ({doc.get('court', '')}, "
            f"{doc.get('date', '')})\n{doc.get('headline', '')}"
            for doc in citing_docs
        )
    else:
        context = "No citing judgments were retrieved from Indian Kanoon."

    prompt = (
        f"TARGET JUDGMENT AS ENTERED: {citation}\n"
        f"CORE CASE NAME: {case_name}\n"
        f"INDIAN KANOON DOCUMENT ID: {target_tid or 'not found'}\n\n"
        f"RETRIEVED JUDGMENTS THAT CITE OR RELATE TO THE TARGET:\n{clip(context, 30000)}\n\n"
        "Assess how Indian courts have treated the target judgment. Return JSON only."
    )

    payload = llm.generate_json(
        prompt,
        provider=provider,
        model=model,
        system=_AUTHORITY_SYSTEM,
        schema_hint=_AUTHORITY_SHAPE,
        temperature=0.1,
        max_tokens=3000,
    )

    status = str(payload.get("status", "UNKNOWN")).upper().strip()
    if status not in STATUS_VALUES:
        status = "UNKNOWN"
    confidence = str(payload.get("confidence", "LOW")).upper().strip()
    if confidence not in ("HIGH", "MEDIUM", "LOW"):
        confidence = "LOW"

    cases = []
    for item in payload.get("citing_cases") or []:
        if not isinstance(item, dict):
            continue
        cases.append(
            {
                "case_name": str(item.get("case_name", "")).strip(),
                "treatment": str(item.get("treatment", "")).strip(),
                "excerpt": str(item.get("excerpt", "")).strip(),
            }
        )

    return {
        "status": status,
        "confidence": confidence,
        "summary": str(payload.get("summary", "")).strip(),
        "citing_cases": cases,
        "retrieved": citing_docs,
        "note": note,
        "kanoon_connected": kanoon.configured(),
        "citation_searched": citation,
        "target_tid": target_tid,
    }
