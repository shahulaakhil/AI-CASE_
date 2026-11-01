"""Text extraction from PDF, DOCX, images and plain text, with vision OCR."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from .. import settings
from ..llm import ImagePart, LLMError, registry as llm

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}

_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

_OCR_PROMPT = (
    "Transcribe every word of text visible in this legal document page, verbatim. "
    "Preserve headings, paragraph numbers, clause numbers, tables and line breaks. "
    "Do not summarise, do not translate, do not add commentary. "
    "If the page is blank, reply with the single word BLANK."
)


@dataclass
class Extraction:
    text: str
    method: str
    pages: int = 0
    filename: str = ""
    warnings: list[str] = field(default_factory=list)
    page_texts: list[tuple[int | None, str]] = field(default_factory=list)

    @property
    def characters(self) -> int:
        return len(self.text)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "method": self.method,
            "method_label": METHOD_LABELS.get(self.method, self.method),
            "pages": self.pages,
            "characters": self.characters,
            "filename": self.filename,
            "warnings": self.warnings,
        }


METHOD_LABELS = {
    "pdf-text": "Digital PDF, text layer read directly",
    "pdf-ocr": "Scanned PDF, read with vision OCR",
    "docx": "Word document, text read directly",
    "docx-ocr": "Word document of images, read with vision OCR",
    "image-ocr": "Image, read with vision OCR",
    "plain-text": "Plain text file",
    "pasted": "Pasted text",
}


def _suffix(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _extract_pdf_content(data: bytes) -> tuple[list[str], set[int]]:
    import fitz

    page_texts: list[str] = []
    image_pages: set[int] = set()
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page_number, page in enumerate(doc, start=1):
            page_texts.append(page.get_text("text"))
            if page.get_images(full=True):
                image_pages.add(page_number)
    return page_texts, image_pages


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    page_texts, _ = _extract_pdf_content(data)
    return "\n\n".join(part for part in page_texts if part.strip()), len(page_texts)


def extract_pdf_pages(data: bytes) -> list[str]:
    page_texts, _ = _extract_pdf_content(data)
    return page_texts


def _pdf_page_images(
    data: bytes,
    page_numbers: Sequence[int],
    dpi: int = 170,
) -> Iterable[tuple[bytes, str]]:
    import fitz

    with fitz.open(stream=data, filetype="pdf") as doc:
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        for page_number in page_numbers:
            pixmap = doc[page_number - 1].get_pixmap(matrix=matrix)
            yield pixmap.tobytes("png"), "image/png"


def extract_docx_text(data: bytes) -> str:
    from docx import Document
    from docx.oxml.ns import qn

    document = Document(io.BytesIO(data))
    parts: list[str] = []
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            parts.append(paragraph.text)
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    if not parts:
        for node in document.element.findall(".//" + qn("w:t")):
            if node.text and node.text.strip():
                parts.append(node.text)
    return "\n".join(parts)


def extract_docx_images(
    data: bytes,
    *,
    limit: int | None = None,
) -> list[tuple[bytes, str]]:
    if limit is not None and limit <= 0:
        return []
    images: list[tuple[bytes, str]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                if name.startswith("word/media/"):
                    mime = _IMAGE_MIME.get(Path(name).suffix.lower(), "image/jpeg")
                    images.append((archive.read(name), mime))
                    if limit is not None and len(images) >= limit:
                        break
    except zipfile.BadZipFile:
        pass
    return images


def _ocr_images(
    images: Iterable[tuple[bytes, str]],
    *,
    provider: str | None,
    model: str | None,
    separator: str,
    numbered_pages: bool = False,
    page_numbers: Sequence[int] | None = None,
) -> tuple[str, list[str], list[tuple[int | None, str]]]:
    parts: list[str] = []
    warnings: list[str] = []
    page_texts: list[tuple[int | None, str]] = []
    for index, (payload, mime) in enumerate(images, start=1):
        page_number = (
            page_numbers[index - 1]
            if page_numbers and index <= len(page_numbers)
            else index if numbered_pages else None
        )
        label_number = page_number if numbered_pages else index
        try:
            text = llm.vision(
                [ImagePart(data=payload, mime_type=mime)],
                _OCR_PROMPT,
                provider=provider,
                model=model,
                max_tokens=4096,
            )
        except LLMError as exc:
            if index == 1:
                raise
            warnings.append(f"{separator} {label_number} could not be read: {exc.message}")
            continue
        if text.strip().upper() == "BLANK":
            continue
        parts.append(f"[{separator} {label_number}]\n{text}")
        page_texts.append((page_number, text))
    return "\n\n".join(parts), warnings, page_texts


def extract(
    data: bytes,
    filename: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    force_ocr: bool = False,
    max_pages: int | None = None,
) -> Extraction:
    """Read a file into plain text, using vision OCR only when needed."""
    suffix = _suffix(filename)
    page_budget = max_pages or settings.MAX_OCR_PAGES
    warnings: list[str] = []

    if suffix == ".pdf":
        pdf_pages, image_pages = _extract_pdf_content(data)
        page_count = len(pdf_pages)
        pages_to_ocr = (
            list(range(1, min(page_count, page_budget) + 1))
            if force_ocr
            else [
                page_number
                for page_number, page_text in enumerate(pdf_pages, start=1)
                if not page_text.strip() and page_number in image_pages and page_number <= page_budget
            ]
        )
        if not pages_to_ocr:
            page_texts = [
                (page_number, page_text)
                for page_number, page_text in enumerate(pdf_pages, start=1)
                if page_text.strip()
            ]
            if not force_ocr and any(
                not page_text.strip() and page_number in image_pages and page_number > page_budget
                for page_number, page_text in enumerate(pdf_pages, start=1)
            ):
                warnings.append(
                    f"Scanned pages after page {page_budget} were not read by OCR. "
                    "Raise MAX_OCR_PAGES to read more."
                )
            return Extraction(
                "\n\n".join(page_text for _, page_text in page_texts),
                "pdf-text",
                page_count,
                filename,
                warnings,
                page_texts=page_texts,
            )

        images = _pdf_page_images(data, pages_to_ocr)
        ocr_text, ocr_warnings, ocr_pages = _ocr_images(
            images,
            provider=provider,
            model=model,
            separator="Page",
            numbered_pages=True,
            page_numbers=pages_to_ocr,
        )
        warnings.extend(ocr_warnings)
        if force_ocr and len(pages_to_ocr) < page_count:
            warnings.append(
                f"Only {len(pages_to_ocr)} page(s) were read by OCR due to the configured limit. "
                "Raise MAX_OCR_PAGES to read more."
            )
        elif not force_ocr and any(
            not page_text.strip() and page_number in image_pages and page_number > page_budget
            for page_number, page_text in enumerate(pdf_pages, start=1)
        ):
            warnings.append(
                f"Scanned pages after page {page_budget} were not read by OCR. "
                "Raise MAX_OCR_PAGES to read more."
            )
        page_text_by_number = {
            page_number: page_text
            for page_number, page_text in enumerate(pdf_pages, start=1)
            if page_text.strip()
        }
        for page_number, page_text in ocr_pages:
            if page_number is not None and len(page_text) > len(page_text_by_number.get(page_number, "")):
                page_text_by_number[page_number] = page_text
        page_texts = sorted(page_text_by_number.items())
        return Extraction(
            "\n\n".join(page_text for _, page_text in page_texts),
            "pdf-ocr",
            page_count,
            filename,
            warnings,
            page_texts,
        )

    if suffix == ".docx":
        text = extract_docx_text(data)
        if text.strip() and not force_ocr:
            return Extraction(text, "docx", 0, filename, page_texts=[(None, text)] if text.strip() else [])
        images = extract_docx_images(data, limit=page_budget)
        if not images:
            return Extraction(text, "docx", 0, filename, page_texts=[(None, text)] if text.strip() else [])
        ocr_text, ocr_warnings, ocr_pages = _ocr_images(
            images, provider=provider, model=model, separator="Image"
        )
        warnings.extend(ocr_warnings)
        combined = ocr_text if len(ocr_text.strip()) > len(text.strip()) else text
        page_texts = ocr_pages if len(ocr_text.strip()) > len(text.strip()) else [(None, text)]
        return Extraction(combined, "docx-ocr", 0, filename, warnings, page_texts)

    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        mime = _IMAGE_MIME.get(suffix, "image/png")
        text, ocr_warnings, page_texts = _ocr_images(
            [(data, mime)], provider=provider, model=model, separator="Image"
        )
        return Extraction(text, "image-ocr", 1, filename, ocr_warnings, page_texts)

    if suffix in {".txt", ".md", ""}:
        text = data.decode("utf-8", errors="replace")
        return Extraction(text, "plain-text", 0, filename, page_texts=[(None, text)])

    raise ValueError(
        f"Unsupported file type '{suffix or filename}'. "
        "Upload a PDF, DOCX, TXT, PNG or JPG file."
    )


def needs_vision(data: bytes, filename: str) -> bool:
    """Report whether a file would require a vision model to be readable."""
    suffix = _suffix(filename)
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return True
    if suffix == ".pdf":
        try:
            page_texts, image_pages = _extract_pdf_content(data)
        except Exception:  # noqa: BLE001 - a broken PDF still needs OCR
            return True
        return any(
            not page_text.strip() and page_number in image_pages
            for page_number, page_text in enumerate(page_texts, start=1)
        )
    if suffix == ".docx":
        try:
            return (
                not extract_docx_text(data).strip()
                and bool(extract_docx_images(data, limit=1))
            )
        except Exception:  # noqa: BLE001
            return True
    return False


def clip(text: str, limit: int) -> str:
    """Trim text for a prompt, keeping a readable ending marker."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[Document truncated at this point for length.]"
