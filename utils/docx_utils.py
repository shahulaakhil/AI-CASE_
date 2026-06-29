"""DOCX document generation helpers for legal documents."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Optional


def _get_doc():
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    return Document, Pt, Inches, RGBColor, WD_ALIGN_PARAGRAPH


def create_list_of_dates_docx(
    rows: list[dict],
    case_title: str = "",
) -> bytes:
    """Generate a court-ready List of Dates as DOCX.

    rows: list of {date, event, source, significance}
    """
    Document, Pt, Inches, RGBColor, WD_ALIGN_PARAGRAPH = _get_doc()
    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.25)
        section.right_margin = Inches(1.25)

    # Title
    title = doc.add_heading("LIST OF DATES AND EVENTS", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if case_title:
        sub = doc.add_paragraph(case_title)
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub.runs[0].bold = True

    doc.add_paragraph("")

    # Table
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(["Date", "Event", "Source", "Significance"]):
        hdr[i].text = h
        hdr[i].paragraphs[0].runs[0].bold = True

    for row in rows:
        cells = table.add_row().cells
        cells[0].text = row.get("date", "")
        cells[1].text = row.get("event", "")
        cells[2].text = row.get("source", "")
        cells[3].text = row.get("significance", "")

    doc.add_paragraph(f"\nGenerated: {datetime.now().strftime('%d %B %Y')}")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def create_judgment_brief_docx(brief: dict, case_name: str = "") -> bytes:
    """Generate a structured judgment brief as DOCX."""
    Document, Pt, Inches, RGBColor, WD_ALIGN_PARAGRAPH = _get_doc()
    doc = Document()

    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.25)
        section.right_margin = Inches(1.25)

    title = doc.add_heading("JUDGMENT BRIEF", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if case_name:
        sub = doc.add_paragraph(case_name)
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub.runs[0].bold = True

    sections = [
        ("Case Details", "case_details"),
        ("Facts", "facts"),
        ("Issues Framed", "issues"),
        ("Arguments — Petitioner / Appellant", "petitioner_arguments"),
        ("Arguments — Respondent", "respondent_arguments"),
        ("Held", "held"),
        ("Ratio Decidendi", "ratio"),
        ("Significance / Precedent Value", "significance"),
    ]
    for heading, key in sections:
        doc.add_heading(heading, level=2)
        content = brief.get(key, "")
        if isinstance(content, list):
            for item in content:
                doc.add_paragraph(f"• {item}", style="List Bullet")
        else:
            doc.add_paragraph(str(content))

    doc.add_paragraph(f"\nGenerated: {datetime.now().strftime('%d %B %Y')}")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def create_legal_document_docx(
    doc_type: str,
    content: str,
    case_title: str = "",
    court: str = "",
) -> bytes:
    """Wrap a drafted legal document text into a formatted DOCX."""
    Document, Pt, Inches, RGBColor, WD_ALIGN_PARAGRAPH = _get_doc()
    doc = Document()

    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.5)
        section.right_margin = Inches(1)

    # Header block
    if court:
        h = doc.add_paragraph(f"IN THE {court.upper()}")
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        h.runs[0].bold = True

    if case_title:
        ct = doc.add_paragraph(case_title)
        ct.alignment = WD_ALIGN_PARAGRAPH.CENTER

    title = doc.add_heading(doc_type.upper(), level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    # Content — preserve paragraph breaks
    for para in content.split("\n"):
        p = doc.add_paragraph(para)
        p.paragraph_format.space_after = Pt(4)

    doc.add_paragraph(f"\nGenerated: {datetime.now().strftime('%d %B %Y')}")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
