"""Text extraction from PDF, DOCX, images and plain text, with vision OCR."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

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


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    page_texts = extract_pdf_pages(data)
    return "\n\n".join(part for part in page_texts if part.strip()), len(page_texts)


def extract_pdf_pages(data: bytes) -> list[str]:
    import fitz

    with fitz.open(stream=data, filetype="pdf") as doc:
        return [page.get_text("text") for page in doc]


def pdf_page_image(data: bytes, page_number: int, dpi: int = 170) -> bytes:
    import fitz

    with fitz.open(stream=data, filetype="pdf") as doc:
        page = doc[page_number]
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pixmap = page.get_pixmap(matrix=matrix)
        return pixmap.tobytes("png")


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


def extract_docx_images(data: bytes) -> list[tuple[bytes, str]]:
    images: list[tuple[bytes, str]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                if name.startswith("word/media/"):
                    mime = _IMAGE_MIME.get(Path(name).suffix.lower(), "image/jpeg")
                    images.append((archive.read(name), mime))
    except zipfile.BadZipFile:
        pass
    return images


def _ocr_images(
    images: list[tuple[bytes, str]],
    *,
    provider: str | None,
    model: str | None,
    separator: str,
    numbered_pages: bool = False,
) -> tuple[str, list[str], list[tuple[int | None, str]]]:
    parts: list[str] = []
    warnings: list[str] = []
    page_texts: list[tuple[int | None, str]] = []
    for index, (payload, mime) in enumerate(images, start=1):
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
            warnings.append(f"{separator} {index} could not be read: {exc.message}")
            continue
        if text.strip().upper() == "BLANK":
            continue
        parts.append(f"[{separator} {index}]\n{text}")
        page_texts.append((index if numbered_pages else None, text))
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
        pdf_pages = extract_pdf_pages(data)
        text = "\n\n".join(part for part in pdf_pages if part.strip())
        page_count = len(pdf_pages)
        needs_ocr = force_ocr or len(text.strip()) < 120
        if not needs_ocr:
            page_texts = [
                (page_number, page_text)
                for page_number, page_text in enumerate(pdf_pages, start=1)
                if page_text.strip()
            ]
            return Extraction(text, "pdf-text", page_count, filename, page_texts=page_texts)

        pages_to_read = min(page_count, page_budget)
        images = [(pdf_page_image(data, i), "image/png") for i in range(pages_to_read)]
        ocr_text, ocr_warnings, ocr_pages = _ocr_images(
            images, provider=provider, model=model, separator="Page", numbered_pages=True
        )
        warnings.extend(ocr_warnings)
        if page_count > pages_to_read:
            warnings.append(
                f"Only the first {pages_to_read} of {page_count} pages were read by OCR. "
                "Raise MAX_OCR_PAGES to read more."
            )
        combined = ocr_text if len(ocr_text.strip()) > len(text.strip()) else text
        page_texts = ocr_pages if len(ocr_text.strip()) > len(text.strip()) else [
            (page_number, page_text)
            for page_number, page_text in enumerate(pdf_pages, start=1)
            if page_text.strip()
        ]
        return Extraction(combined, "pdf-ocr", page_count, filename, warnings, page_texts)

    if suffix == ".docx":
        text = extract_docx_text(data)
        if len(text.strip()) >= 60 and not force_ocr:
            return Extraction(text, "docx", 0, filename, page_texts=[(None, text)] if text.strip() else [])
        images = extract_docx_images(data)[:page_budget]
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
            text, _ = extract_pdf_text(data)
        except Exception:  # noqa: BLE001 - a broken PDF still needs OCR
            return True
        return len(text.strip()) < 120
    if suffix == ".docx":
        try:
            return len(extract_docx_text(data).strip()) < 60
        except Exception:  # noqa: BLE001
            return True
    return False


def clip(text: str, limit: int) -> str:
    """Trim text for a prompt, keeping a readable ending marker."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[Document truncated at this point for length.]"
