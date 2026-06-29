"""Tool 1: List of Dates generator.

Extracts all material dates and events from case files, pleadings, FIRs,
charge sheets, witness statements, and judgments, then outputs a court-ready
chronological table.
"""
from __future__ import annotations

import json
from typing import Optional

from .llm import gemini_json, gemini_generate

_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "date": {"type": "string"},
            "event": {"type": "string"},
            "source": {"type": "string"},
            "significance": {"type": "string"},
        },
        "required": ["date", "event", "source", "significance"],
    },
}

_SYSTEM = """You are a senior litigation paralegal specialising in Indian courts.
Your task is to extract every material date and corresponding event from the
provided legal document(s). Be exhaustive — do not miss any date.

Rules:
1. Dates must be real dates found in the text (do not invent).
2. Describe the event concisely in legal language (max 25 words).
3. 'source' is the document section or paragraph where the date appears.
4. 'significance' is a one-line legal significance (e.g., "Filing of FIR", "Date of cause of action").
5. Sort chronologically in the JSON you return.
6. If a date is approximate (e.g., "sometime in January 2022"), include it with a note.
"""


def extract_list_of_dates(text: str, case_title: str = "") -> list[dict]:
    """Extract dates from document text and return sorted chronological list."""
    context = f"Case: {case_title}\n\n" if case_title else ""
    prompt = (
        f"{context}Extract all material dates and events from the following legal document. "
        f"Return a JSON array sorted chronologically.\n\n"
        f"DOCUMENT:\n{text[:20000]}"
    )
    result = gemini_json(
        prompt,
        schema=_SCHEMA,
        system_instruction=_SYSTEM,
        max_output_tokens=4096,
        temperature=0.1,
    )
    if isinstance(result, list):
        return result
    return []


def ocr_and_extract(
    file_bytes: bytes,
    filename: str,
    case_title: str = "",
) -> tuple[list[dict], str]:
    """Extract text (with OCR fallback) then extract dates. Returns (rows, method)."""
    from utils.pdf_utils import (
        extract_text_auto, pdf_page_count, pdf_page_to_image_bytes,
        extract_images_from_docx,
    )
    from .llm import gemini_vision

    text, method = extract_text_auto(file_bytes, filename)

    if method in ("pdf-scanned", "docx-scanned") or len(text.strip()) < 50:
        if method == "docx-scanned":
            images = extract_images_from_docx(file_bytes)
            ocr_parts = []
            for i, (img_bytes, mime) in enumerate(images[:5]):
                page_text = gemini_vision(
                    img_bytes,
                    "Extract ALL text verbatim from this legal document image. "
                    "Preserve structure, headings, and paragraph breaks.",
                    mime_type=mime,
                )
                ocr_parts.append(page_text)
            text = "\n\n--- IMAGE BREAK ---\n\n".join(ocr_parts)
            method = "ocr-gemini"
        elif filename.lower().endswith(".pdf"):
            n_pages = min(pdf_page_count(file_bytes), 5)
            ocr_parts = []
            for i in range(n_pages):
                img = pdf_page_to_image_bytes(file_bytes, page_num=i)
                page_text = gemini_vision(
                    img,
                    "Extract ALL text verbatim from this legal document page. "
                    "Preserve structure, headings, and paragraph breaks.",
                    mime_type="image/png",
                )
                ocr_parts.append(page_text)
            text = "\n\n--- PAGE BREAK ---\n\n".join(ocr_parts)
            method = "ocr-gemini"

    rows = extract_list_of_dates(text, case_title)
    return rows, method
