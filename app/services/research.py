"""Legal Research, Prompt Enhancer, Translation and document question answering."""
from __future__ import annotations

from typing import Any

from ..llm import registry as llm
from . import kanoon
from .documents import clip

# ---------------------------------------------------------------------------
# Tool 2: Legal Research
# ---------------------------------------------------------------------------

_ROUTER_SYSTEM = """You turn a lawyer's question into a search plan for Indian case law.

Classify the intent as one of STATUTE, CASE_LAW, PROCEDURE, GENERAL.
Identify the jurisdiction if one is implied, the statutes involved, and the core legal
concepts. Then write a short keyword query suitable for the Indian Kanoon search box.
The query should be five to twelve keywords, not a sentence."""

_ROUTER_SHAPE = """{"intent": "", "jurisdiction": "", "acts": [""], "concepts": [""],
 "kanoon_query": ""}"""

_RESEARCH_SYSTEM = """You are a senior advocate practising before the Supreme Court of India.
Answer research questions the way a good junior brief would.

Structure every answer with these headings:
### Short answer
### Statutory position
### Case law
### Application to the facts
### Risks and open points

Rules:
1. Ground the answer in the retrieved context wherever it is on point, citing a source as
   [Source 1], [Source 2] and naming the case.
2. Where the retrieved context is not on point, answer from your own knowledge of Indian
   law and say clearly that the citation is from memory rather than from retrieval.
3. Never invent a case name, a citation, a section number or statutory text. If you are
   not certain of a citation, write it as [verify: what needs checking].
4. Give section numbers whenever you name a statute.
5. Be concrete and practical. A litigator should be able to act on the answer."""

_DOC_QA_SYSTEM = """You help an Indian advocate find the exact passages in a document that
bear on a specific question or argument.

For every relevant passage:
1. Give the paragraph number, page number or heading where it appears.
2. Quote or closely paraphrase the passage.
3. Label it SUPPORTS, CONTRADICTS or CONTEXT.

If nothing in the document is relevant, say NOT RELEVANT and explain in one line why.
Never summarise the whole document. Never rely on anything outside the document."""


def _history_block(history: list[dict] | None, limit: int = 4) -> str:
    if not history:
        return ""
    lines = ["\nEARLIER EXCHANGES IN THIS CONVERSATION:"]
    for item in history[-limit:]:
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if not question:
            continue
        lines.append(f"Q: {question}")
        lines.append(f"A: {answer[:700]}")
    return "\n".join(lines) + "\n" if len(lines) > 1 else ""


def research(
    question: str,
    *,
    max_results: int = 5,
    history: list[dict] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    routing: dict[str, Any] = {
        "intent": "GENERAL",
        "jurisdiction": "",
        "acts": [],
        "concepts": [],
        "kanoon_query": question,
    }
    if kanoon.configured():
        try:
            payload = llm.generate_json(
                question,
                provider=provider,
                model=model,
                system=_ROUTER_SYSTEM,
                schema_hint=_ROUTER_SHAPE,
                temperature=0.0,
                max_tokens=600,
            )
            if isinstance(payload, dict):
                routing.update({k: v for k, v in payload.items() if v})
        except Exception:  # noqa: BLE001 - routing is a nicety, never fatal
            pass

    search_query = str(routing.get("kanoon_query") or question)[:300]
    results = kanoon.search(search_query)
    docs = results.get("docs", [])[: max(1, min(max_results, 10))]

    if docs:
        context = "\n\n".join(
            f"[Source {index}] {doc.get('title', '')}"
            + (f" [{doc['citation']}]" if doc.get("citation") else "")
            + f"\nCourt: {doc.get('court', 'not stated')}. Date: {doc.get('date', 'not stated')}."
            + f"\n{doc.get('headline', '')}"
            for index, doc in enumerate(docs, start=1)
        )
    else:
        context = "No judgments were retrieved. Answer from your own knowledge of Indian law."

    prompt = (
        f"RETRIEVED CONTEXT FROM INDIAN KANOON:\n{clip(context, 24000)}\n"
        f"{_history_block(history)}\n"
        f"LEGAL QUESTION:\n{question}\n\n"
        "Answer using the required headings."
    )

    answer = llm.generate(
        prompt,
        provider=provider,
        model=model,
        system=_RESEARCH_SYSTEM,
        temperature=0.2,
        max_tokens=5000,
    )

    sources = [
        {
            "n": index,
            "title": doc.get("title", ""),
            "headline": doc.get("headline", ""),
            "citation": doc.get("citation", ""),
            "court": doc.get("court", ""),
            "date": doc.get("date", ""),
            "tid": doc.get("tid", ""),
            "url": doc.get("url", ""),
        }
        for index, doc in enumerate(docs, start=1)
    ]

    return {
        "answer": answer,
        "sources": sources,
        "intent": str(routing.get("intent", "GENERAL")).upper(),
        "search_query": search_query,
        "note": results.get("note", ""),
        "kanoon_connected": kanoon.configured(),
        "total_found": results.get("total_count", 0),
    }


def ask_document(
    question: str,
    document_text: str,
    *,
    document_name: str = "",
    history: list[dict] | None = None,
    provider: str | None = None,
    model: str | None = None,
    system: str | None = None,
) -> str:
    prompt = (
        f"DOCUMENT NAME: {document_name or 'uploaded document'}\n\n"
        f"---BEGIN DOCUMENT---\n{clip(document_text, 90000)}\n---END DOCUMENT---\n"
        f"{_history_block(history)}\n"
        f"QUESTION: {question}"
    )
    return llm.generate(
        prompt,
        provider=provider,
        model=model,
        system=system or _DOC_QA_SYSTEM,
        temperature=0.1,
        max_tokens=4000,
    )


# ---------------------------------------------------------------------------
# Tool 5: Prompt Enhancer
# ---------------------------------------------------------------------------

_CATEGORIES = (
    "CONSTITUTIONAL", "CONTRACT", "TORT", "CRIMINAL", "FAMILY", "PROPERTY", "IPR",
    "CONSUMER", "LABOUR", "TAX", "CORPORATE", "ARBITRATION", "PROCEDURE", "EVIDENCE",
    "OTHER",
)

_ENHANCER_SYSTEM = """You are a prompt engineer for legal AI used by Indian advocates.

Rewrite the lawyer's raw question into a structured research instruction that will get a
far better answer from any large language model.

The rewritten prompt must contain these five labelled parts:
CONTEXT            The legal situation, the forum, and the branch of law in play.
QUESTIONS          Three to five precise sub questions, numbered.
OUTPUT FORMAT      Exactly what the answer should contain and in what order.
CONSTRAINTS        Jurisdiction, date range, court hierarchy, anything to exclude.
STYLE              The register expected, for example a court ready research note.

Write the rewritten prompt so it can be copied and pasted as is. Do not answer the legal
question itself. After the prompt, on its own final line, write:
Enhancement note: one sentence on what you changed and why."""

_CLASSIFY_SHAPE = """{"categories": [""], "jurisdiction": ""}"""


def enhance_prompt(
    raw_query: str, *, provider: str | None = None, model: str | None = None
) -> dict:
    classification = {"categories": ["OTHER"], "jurisdiction": "Indian courts"}
    try:
        payload = llm.generate_json(
            f"Classify this Indian legal query.\n\nQUERY: {raw_query}",
            provider=provider,
            model=model,
            system=(
                "Classify an Indian legal query into one or more of these categories: "
                + ", ".join(_CATEGORIES)
                + ". Also name the likely forum, one of Supreme Court, High Court, "
                "District Court, Tribunal, Arbitral Tribunal or Consumer Commission."
            ),
            schema_hint=_CLASSIFY_SHAPE,
            temperature=0.0,
            max_tokens=400,
        )
        if isinstance(payload, dict):
            categories = payload.get("categories")
            if isinstance(categories, list) and categories:
                classification["categories"] = [str(c).upper().strip() for c in categories][:4]
            if payload.get("jurisdiction"):
                classification["jurisdiction"] = str(payload["jurisdiction"]).strip()
    except Exception:  # noqa: BLE001 - classification is optional
        pass

    prompt = (
        f"RAW QUERY FROM THE LAWYER:\n{raw_query}\n\n"
        f"DETECTED AREA OF LAW: {', '.join(classification['categories'])}\n"
        f"LIKELY FORUM: {classification['jurisdiction']}\n\n"
        "Produce the structured research prompt now."
    )
    enhanced = llm.generate(
        prompt,
        provider=provider,
        model=model,
        system=_ENHANCER_SYSTEM,
        temperature=0.3,
        max_tokens=2500,
    )

    note = ""
    lines = enhanced.strip().splitlines()
    for index in range(len(lines) - 1, -1, -1):
        candidate = lines[index].strip().lstrip("*# ").strip()
        if candidate.lower().startswith("enhancement note"):
            note = candidate.split(":", 1)[-1].strip()
            enhanced = "\n".join(lines[:index]).strip()
            break

    return {
        "enhanced_prompt": enhanced,
        "enhancement_note": note,
        "categories": classification["categories"],
        "jurisdiction": classification["jurisdiction"],
    }


# ---------------------------------------------------------------------------
# Tool 4: Translation
# ---------------------------------------------------------------------------

_TRANSLATE_SYSTEM = """You are a certified legal translator working with Indian court documents.
You translate from Hindi, Bengali, Marathi, Tamil, Telugu, Kannada, Malayalam, Gujarati,
Punjabi, Urdu, Odia, Assamese and other languages into English.

Preserve exactly:
1. Legal terminology and terms of art, with the original term in brackets where the English
   is not a settled equivalent.
2. Document structure, headings, and every paragraph and clause number.
3. Party names, place names and court names, transliterated rather than translated.
4. Figures, dates and amounts, unchanged.

Use the formal register of an Indian court filing. After the translation, add a short
section headed "Translator's note" listing any term that was ambiguous and how you read it.
If the document is already in English, return it cleanly formatted and say so in the note."""

_DOC_CHAT_SYSTEM = """You are a legal analyst answering questions about one specific document.

Answer only from the document supplied, including its English translation where one exists.
Cite the paragraph number, clause number, page or heading for every point you make.
If the document does not answer the question, say so plainly instead of speculating."""


def detect_language(
    text: str, *, provider: str | None = None, model: str | None = None
) -> str:
    sample = text.strip()[:600]
    if not sample:
        return "unknown"
    result = llm.generate(
        f"Identify the language of this text. Reply with the English name of the language "
        f"and nothing else.\n\n{sample}",
        provider=provider,
        model=model,
        temperature=0.0,
        max_tokens=20,
    )
    return result.strip().strip(".").splitlines()[0][:40] or "unknown"


def translate_to_english(
    text: str,
    *,
    source_language: str = "",
    provider: str | None = None,
    model: str | None = None,
) -> str:
    header = f"Source language: {source_language}.\n" if source_language else ""
    return llm.generate(
        f"{header}Translate the legal document below into English.\n\n"
        f"DOCUMENT:\n{clip(text, 60000)}",
        provider=provider,
        model=model,
        system=_TRANSLATE_SYSTEM,
        temperature=0.1,
        max_tokens=8000,
    )


def chat_with_document(
    question: str,
    original_text: str,
    translated_text: str = "",
    *,
    history: list[dict] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    body = translated_text.strip() or original_text
    if translated_text.strip() and original_text.strip():
        body = (
            f"ENGLISH TRANSLATION:\n{clip(translated_text, 55000)}\n\n"
            f"ORIGINAL TEXT (first part):\n{clip(original_text, 12000)}"
        )
    return ask_document(
        question,
        body,
        history=history,
        provider=provider,
        model=model,
        system=_DOC_CHAT_SYSTEM,
    )
