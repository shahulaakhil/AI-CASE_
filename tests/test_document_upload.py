from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
from docx import Document
from fastapi.testclient import TestClient

from app import db, settings
from app.llm import LLMError
from app.main import app
from app.services import documents, rag


def make_pdf(pages: list[str], *, scanned_pages: set[int] | None = None) -> bytes:
    scanned_pages = scanned_pages or set()
    pdf = fitz.open()
    image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10))
    image.clear_with(255)
    image_bytes = image.tobytes("png")
    for page_number, text in enumerate(pages, start=1):
        page = pdf.new_page()
        if text:
            page.insert_text((72, 72), text)
        if page_number in scanned_pages:
            page.insert_image(page.rect, stream=image_bytes)
    payload = pdf.tobytes()
    pdf.close()
    return payload


def make_docx(*, text: str = "", table: list[list[str]] | None = None) -> bytes:
    document = Document()
    if text:
        document.add_paragraph(text)
    if table:
        word_table = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for column_index, value in enumerate(row):
                word_table.cell(row_index, column_index).text = value
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


class DocumentExtractionTests(unittest.TestCase):
    def test_short_text_pdf_is_read_without_forcing_vision_ocr(self) -> None:
        pdf = make_pdf(["A short but readable judgment."])
        with patch("app.services.documents._ocr_images", side_effect=AssertionError):
            result = documents.extract(pdf, "short.pdf")

        self.assertEqual(result.method, "pdf-text")
        self.assertIn("short but readable judgment", result.text)
        self.assertEqual(result.page_texts[0][0], 1)
        self.assertFalse(documents.needs_vision(pdf, "short.pdf"))

    def test_mixed_pdf_ocr_is_limited_to_scanned_pages_with_actual_page_numbers(self) -> None:
        pdf = make_pdf(
            ["Readable text on page one.", ""],
            scanned_pages={2},
        )
        with patch(
            "app.services.documents.llm.vision",
            return_value="Text recovered from the scanned second page.",
        ) as vision:
            result = documents.extract(pdf, "mixed.pdf", provider="gemini")

        self.assertEqual(result.method, "pdf-ocr")
        self.assertEqual(
            [page for page, _ in result.page_texts],
            [1, 2],
        )
        self.assertIn("scanned second page", result.text)
        self.assertTrue(documents.needs_vision(pdf, "mixed.pdf"))
        vision.assert_called_once()

    def test_docx_text_and_table_content_are_extracted(self) -> None:
        docx = make_docx(
            text="The court considered the written notice.",
            table=[["Issue", "Finding"], ["Notice", "Required"]],
        )
        result = documents.extract(docx, "judgment.docx")

        self.assertIn("written notice", result.text)
        self.assertIn("Issue | Finding", result.text)
        self.assertIn("Notice | Required", result.text)
        self.assertEqual(result.method, "docx")


class DocumentUploadApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sqlite_path = settings.SQLITE_PATH
        self.db_initialised = db._initialised
        settings.SQLITE_PATH = Path(self.temp_dir.name) / "upload-test.db"
        db._initialised = False

    def tearDown(self) -> None:
        settings.SQLITE_PATH = self.sqlite_path
        db._initialised = self.db_initialised
        self.temp_dir.cleanup()

    @staticmethod
    def fake_embeddings(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def test_valid_pdf_upload_extracts_text_and_indexes_metadata(self) -> None:
        pdf = make_pdf(["The court held that written notice is required."])
        with (
            patch("app.services.rag.embed_texts", side_effect=self.fake_embeddings),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/extract",
                files={"file": ("judgment.pdf", pdf, "application/pdf")},
                data={"index_judgment": "true"},
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["text"])
        self.assertTrue(result["rag_indexed"])
        stored = db.judgment(result["document_id"])
        chunks = db.judgment_chunks(result["document_id"])
        self.assertEqual(stored["filename"], "judgment.pdf")
        self.assertEqual(chunks[0]["page_number"], 1)

    def test_valid_docx_upload_returns_extracted_text(self) -> None:
        docx = make_docx(text="The court allowed the appeal.")
        with TestClient(app) as client:
            response = client.post(
                "/api/extract",
                files={
                    "file": (
                        "judgment.docx",
                        docx,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["method"], "docx")
        self.assertIn("allowed the appeal", response.json()["text"])

    def test_empty_upload_returns_a_meaningful_client_error(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/extract",
                files={"file": ("empty.pdf", b"", "application/pdf")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["error"]["message"],
            "The uploaded file is empty.",
        )

    def test_oversized_upload_is_rejected_before_full_read(self) -> None:
        with (
            patch.object(settings, "MAX_UPLOAD_MB", 1),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/extract",
                files={"file": ("large.txt", b"x" * (1024 * 1024 + 8), "text/plain")},
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn("exceeds", response.json()["detail"]["error"]["message"])

    def test_malformed_pdf_returns_safe_read_error(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/extract",
                files={"file": ("broken.pdf", b"not a PDF", "application/pdf")},
            )

        self.assertEqual(response.status_code, 422)
        error = response.json()["detail"]["error"]
        self.assertEqual(
            error["message"],
            "The uploaded file is not a valid or readable document.",
        )
        self.assertNotIn("not a PDF", str(error))

    def test_malformed_docx_returns_safe_read_error(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/extract",
                files={"file": ("broken.docx", b"not a DOCX", "application/octet-stream")},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"]["error"]["message"],
            "The uploaded file is not a valid or readable document.",
        )

    def test_empty_readable_document_is_not_reported_as_success(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/extract",
                files={"file": ("blank.pdf", make_pdf([""]), "application/pdf")},
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("No readable text", response.json()["detail"]["error"]["message"])

    def test_ocr_provider_failure_returns_structured_502_error(self) -> None:
        with (
            patch(
                "app.api.routes.documents.extract",
                side_effect=LLMError(
                    "The selected provider has no vision model configured.",
                    provider="groq",
                    hint="Choose a vision-capable model.",
                ),
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/extract",
                files={"file": ("scan.pdf", make_pdf([""]), "application/pdf")},
            )

        self.assertEqual(response.status_code, 502)
        error = response.json()["detail"]["error"]
        self.assertIn("no vision model", error["message"])
        self.assertEqual(error["hint"], "Choose a vision-capable model.")

    def test_rag_index_failure_is_explicit_without_losing_extracted_text(self) -> None:
        pdf = make_pdf(["Text remains available for the existing summarizer."])
        with (
            patch(
                "app.services.rag.embed_texts",
                side_effect=rag.EmbeddingError("Model cache is unavailable."),
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/extract",
                files={"file": ("judgment.pdf", pdf, "application/pdf")},
                data={"index_judgment": "true"},
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["text"])
        self.assertFalse(result["rag_indexed"])
        self.assertIn("Model cache is unavailable", result["rag_error"])
        self.assertNotIn("document_id", result)


if __name__ == "__main__":
    unittest.main()
