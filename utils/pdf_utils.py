"""PDF/DOCX text extraction and OCR helpers."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF using PyMuPDF. Returns concatenated page text."""
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text("text")
            if text.strip():
                pages.append(text)
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}") from e


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX file (paragraphs + table cells)."""
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(io.BytesIO(file_bytes))

    parts = []
    # Paragraphs
    for p in doc.paragraphs:
        if p.text.strip():
            parts.append(p.text)
    # Table cells
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text)
    # Fallback: raw w:t elements (catches text in text boxes / drawing objects)
    if not parts:
        for t_elem in doc._element.findall('.//' + qn('w:t')):
            if t_elem.text and t_elem.text.strip():
                parts.append(t_elem.text)

    return "\n".join(parts)


def is_scanned_pdf(file_bytes: bytes, min_text_ratio: float = 0.1) -> bool:
    """Return True if the PDF is mostly scanned (little selectable text)."""
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_chars = sum(len(page.get_text("text")) for page in doc)
        doc.close()
        return total_chars < (len(file_bytes) * min_text_ratio)
    except Exception:
        return True


def pdf_page_to_image_bytes(file_bytes: bytes, page_num: int = 0, dpi: int = 200) -> bytes:
    """Render a PDF page to PNG bytes for Gemini Vision OCR."""
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    doc.close()
    return pix.tobytes("png")


def pdf_page_count(file_bytes: bytes) -> int:
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    n = doc.page_count
    doc.close()
    return n


def extract_images_from_docx(file_bytes: bytes) -> list[tuple[bytes, str]]:
    """Extract all embedded images from a DOCX (which is a ZIP).

    Returns list of (image_bytes, mime_type) tuples.
    """
    images = []
    ext_to_mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            for name in z.namelist():
                if name.startswith("word/media/"):
                    ext = Path(name).suffix.lower()
                    mime = ext_to_mime.get(ext, "image/jpeg")
                    images.append((z.read(name), mime))
    except Exception:
        pass
    return images


def extract_text_auto(file_bytes: bytes, filename: str) -> tuple[str, str]:
    """Auto-detect file type and extract text. Returns (text, method).

    Methods:
      "docx"         — normal DOCX with readable text
      "docx-scanned" — DOCX containing only embedded images (no selectable text)
      "pdf-text"     — digital PDF with selectable text
      "pdf-scanned"  — scanned/image-only PDF
      "raw-text"     — plain text fallback
    """
    fname = filename.lower()
    if fname.endswith(".docx"):
        text = extract_text_from_docx(file_bytes)
        if len(text.strip()) > 50:
            return text, "docx"
        # No readable text — might be an image-based DOCX
        images = extract_images_from_docx(file_bytes)
        if images:
            return "", "docx-scanned"
        return text, "docx"
    elif fname.endswith(".pdf"):
        text = extract_text_from_pdf(file_bytes)
        if len(text.strip()) > 100:
            return text, "pdf-text"
        return text, "pdf-scanned"
    else:
        return file_bytes.decode("utf-8", errors="replace"), "raw-text"
