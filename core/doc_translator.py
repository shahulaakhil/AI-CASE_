"""Tool 4: Translation + OCR + Ask AI.

1. Accept uploaded document (PDF/image, any language)
2. Extract text via PyMuPDF (digital PDF) or Gemini Vision (scanned/image)
3. Detect language and translate to English if needed
4. Provide an interactive Ask AI feature over the document
"""
from __future__ import annotations

from .llm import gemini_generate, gemini_vision

_TRANSLATE_SYSTEM = """You are a professional legal translator with expertise in
Indian languages (Hindi, Bengali, Marathi, Tamil, Telugu, Kannada, Malayalam,
Gujarati, Punjabi, Urdu, Odia) and English.

Translate the provided legal document to English. Preserve:
- Legal terminology and technical terms
- Document structure (headings, numbered paragraphs)
- Party names (transliterate, do not translate)
- Section/clause numbers exactly as they appear
- Formal register appropriate for Indian courts

After the translation, add a brief "Translator's Note" if any terms were ambiguous."""

_ASK_SYSTEM = """You are a senior legal analyst. You have access to a legal document
(and its English translation if originally in another language).

Answer the user's question based strictly on the document content.
If the answer is not in the document, say so explicitly.
Provide inline references (paragraph numbers, page numbers, section headings)
wherever possible. Do NOT speculate beyond what is in the document."""


def detect_language(text: str) -> str:
    """Detect the language of the text using Gemini."""
    if not text.strip():
        return "unknown"
    prompt = (
        f"Identify the language of the following text. "
        f"Reply with ONLY the language name in English (e.g., 'Hindi', 'English', 'Bengali').\n\n"
        f"{text[:500]}"
    )
    return gemini_generate(prompt, max_output_tokens=20, temperature=0.0).strip()


def translate_to_english(text: str, source_language: str = "") -> str:
    """Translate legal document text to English."""
    lang_note = f"Source language: {source_language}. " if source_language else ""
    prompt = (
        f"{lang_note}Translate the following legal document to English.\n\n"
        f"DOCUMENT:\n{text[:20000]}"
    )
    return gemini_generate(
        prompt,
        system_instruction=_TRANSLATE_SYSTEM,
        temperature=0.1,
        max_output_tokens=8192,
    )


def ocr_extract(file_bytes: bytes, filename: str) -> tuple[str, str]:
    """Extract text from a file. Returns (text, method)."""
    from utils.pdf_utils import (
        extract_text_auto, pdf_page_count, pdf_page_to_image_bytes,
        extract_images_from_docx,
    )

    text, method = extract_text_auto(file_bytes, filename)

    if method in ("pdf-scanned", "docx-scanned") or len(text.strip()) < 50:
        if method == "docx-scanned":
            # OCR embedded images from DOCX
            images = extract_images_from_docx(file_bytes)
            parts = []
            for i, (img_bytes, mime) in enumerate(images[:8]):
                page_text = gemini_vision(
                    img_bytes,
                    "Extract ALL text from this legal document page verbatim. "
                    "Preserve structure, headings, numbering and paragraph breaks.",
                    mime_type=mime,
                )
                parts.append(f"[Image {i+1}]\n{page_text}")
            text = "\n\n".join(parts)
            method = "ocr-vision"
        elif filename.lower().endswith(".pdf"):
            n_pages = min(pdf_page_count(file_bytes), 8)
            parts = []
            for i in range(n_pages):
                img = pdf_page_to_image_bytes(file_bytes, page_num=i)
                page_text = gemini_vision(
                    img,
                    "Extract ALL text from this legal document page verbatim. "
                    "Preserve structure, headings, numbering and paragraph breaks.",
                    mime_type="image/png",
                )
                parts.append(f"[Page {i+1}]\n{page_text}")
            text = "\n\n".join(parts)
            method = "ocr-vision"
        else:
            img_bytes = file_bytes
            ext = filename.lower().rsplit(".", 1)[-1]
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/png")
            text = gemini_vision(
                img_bytes,
                "Extract ALL text from this legal document image verbatim.",
                mime_type=mime,
            )
            method = "ocr-vision"

    return text, method


def ask_document(
    question: str,
    original_text: str,
    translated_text: str = "",
) -> str:
    """Answer a question about the document content."""
    doc_section = translated_text if translated_text else original_text
    prompt = (
        f"DOCUMENT CONTENT:\n{doc_section[:15000]}\n\n"
        f"QUESTION: {question}\n\n"
        "Answer based strictly on the document above."
    )
    return gemini_generate(
        prompt,
        system_instruction=_ASK_SYSTEM,
        temperature=0.1,
        max_output_tokens=2048,
    )
