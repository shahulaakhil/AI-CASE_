"""Tool 8: Judgment Summariser.

Produces structured briefs from Indian court judgments.
Format: Case Details → Facts → Issues → Arguments → Held → Ratio → Significance.
"""
from __future__ import annotations

from .llm import gemini_json, gemini_generate

_SCHEMA = {
    "type": "object",
    "properties": {
        "case_details": {
            "type": "object",
            "properties": {
                "case_name": {"type": "string"},
                "citation": {"type": "string"},
                "court": {"type": "string"},
                "bench": {"type": "string"},
                "date_of_judgment": {"type": "string"},
                "subject_matter": {"type": "string"},
            },
        },
        "facts": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {"type": "string"},
        },
        "petitioner_arguments": {"type": "string"},
        "respondent_arguments": {"type": "string"},
        "held": {"type": "string"},
        "ratio": {"type": "string"},
        "significance": {"type": "string"},
        "key_statutes_cited": {
            "type": "array",
            "items": {"type": "string"},
        },
        "key_cases_cited": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "case_details", "facts", "issues",
        "petitioner_arguments", "respondent_arguments",
        "held", "ratio", "significance",
    ],
}

_SYSTEM = """You are a senior judicial clerk at the Supreme Court of India.
Summarise the provided judgment into a structured brief for a practising advocate.

Rules:
1. Be precise and complete — this is a professional legal document.
2. Facts: Include all material facts chronologically.
3. Issues: List each question of law/fact framed by the court as a numbered question.
4. Arguments: Summarise each side's key contentions with the statutory/case basis.
5. Held: State the final order/decree precisely.
6. Ratio decidendi: State the legal principle(s) established, clearly and concisely.
7. Significance: Explain why this judgment matters for Indian law.
8. Do not add information not found in the judgment.
9. For the citation, look for "AIR", "SCC", "SCR", "Supp SCR", or "(YEAR) X Y Z" format."""


def summarise_judgment(text: str) -> dict:
    """Summarise a judgment. Returns structured dict matching _SCHEMA."""
    prompt = (
        f"Summarise this judgment into a structured brief. "
        f"Return JSON matching the schema.\n\n"
        f"JUDGMENT TEXT:\n{text[:25000]}"
    )
    try:
        result = gemini_json(
            prompt,
            schema=_SCHEMA,
            system_instruction=_SYSTEM,
            temperature=0.1,
            max_output_tokens=6000,
        )
    except Exception as e:
        # Fall back to plain text summary
        plain = gemini_generate(
            f"Summarise this judgment in structured format (Facts, Issues, Held, Ratio, Significance):\n\n{text[:20000]}",
            system_instruction=_SYSTEM,
            temperature=0.1,
            max_output_tokens=4096,
        )
        result = {
            "case_details": {"case_name": "See below", "citation": "", "court": "", "bench": "", "date_of_judgment": "", "subject_matter": ""},
            "facts": plain,
            "issues": [],
            "petitioner_arguments": "",
            "respondent_arguments": "",
            "held": "",
            "ratio": "",
            "significance": "",
        }
    return result


def ocr_and_summarise(file_bytes: bytes, filename: str) -> tuple[dict, str]:
    """Extract text from judgment file and summarise. Returns (brief, method)."""
    from utils.pdf_utils import (
        extract_text_auto, pdf_page_count, pdf_page_to_image_bytes,
        extract_images_from_docx,
    )
    from .llm import gemini_vision

    text, method = extract_text_auto(file_bytes, filename)

    if method in ("pdf-scanned", "docx-scanned") or len(text.strip()) < 100:
        if method == "docx-scanned":
            images = extract_images_from_docx(file_bytes)
            parts = []
            for i, (img_bytes, mime) in enumerate(images[:8]):
                page_text = gemini_vision(
                    img_bytes,
                    "Extract ALL text from this judgment page verbatim. Preserve paragraph structure.",
                    mime_type=mime,
                )
                parts.append(page_text)
            text = "\n\n--- IMAGE BREAK ---\n\n".join(parts)
            method = "ocr-vision"
        elif filename.lower().endswith(".pdf"):
            n_pages = min(pdf_page_count(file_bytes), 10)
            parts = []
            for i in range(n_pages):
                img = pdf_page_to_image_bytes(file_bytes, page_num=i)
                page_text = gemini_vision(
                    img,
                    "Extract ALL text from this judgment page verbatim. Preserve paragraph structure.",
                    mime_type="image/png",
                )
                parts.append(page_text)
            text = "\n\n".join(parts)
            method = "ocr-vision"

    brief = summarise_judgment(text)
    return brief, method
