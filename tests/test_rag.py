from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import db, settings
from app.services import analysis, rag


class JudgmentRagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sqlite_path = settings.SQLITE_PATH
        self.db_initialised = db._initialised
        settings.SQLITE_PATH = Path(self.temp_dir.name) / "rag-test.db"
        db._initialised = False

    def tearDown(self) -> None:
        settings.SQLITE_PATH = self.sqlite_path
        db._initialised = self.db_initialised
        self.temp_dir.cleanup()

    @staticmethod
    def fake_embeddings(texts: list[str]) -> list[list[float]]:
        return [
            [0.0, 1.0] if "unrelated" in text.lower() or "boiling point" in text.lower()
            else [1.0, 0.0]
            for text in texts
        ]

    def test_chunks_preserve_pdf_page_numbers(self) -> None:
        chunks = rag.make_chunks(
            "The first page finding.",
            [(1, "The first page finding."), (2, "The second page finding.")],
        )

        self.assertEqual([(chunk["page_number"], chunk["text"]) for chunk in chunks], [
            (1, "The first page finding."),
            (2, "The second page finding."),
        ])

    def test_embeddings_use_configured_local_model(self) -> None:
        encoder = SimpleNamespace(embed=Mock(return_value=iter([[0.25, 0.75]])))
        with patch("app.services.rag._get_embedding_model", return_value=encoder):
            vectors = rag.embed_texts(["judgment passage"])

        self.assertEqual(vectors, [[0.25, 0.75]])
        encoder.embed.assert_called_once_with(["judgment passage"], batch_size=1)

    def test_model_loader_uses_minilm_and_persistent_cache_directory(self) -> None:
        encoder = object()
        model_name = "sentence-transformers/all-MiniLM-L6-v2"
        cache_dir = Path(self.temp_dir.name) / "models" / "fastembed"
        with (
            patch("fastembed.TextEmbedding", return_value=encoder) as constructor,
            patch.object(settings, "DATA_DIR", Path(self.temp_dir.name)),
            patch.object(settings, "EMBEDDING_MODEL", model_name),
            patch.object(rag, "_embedding_instance", None),
            patch.object(rag, "_embedding_instance_name", ""),
        ):
            model = rag._get_embedding_model()

        self.assertIs(model, encoder)
        constructor.assert_called_once_with(
            model_name=model_name,
            cache_dir=str(cache_dir),
        )

    def test_local_embedding_does_not_require_an_api_key(self) -> None:
        with (
            patch("importlib.util.find_spec", return_value=object()),
            patch.object(settings, "HUGGINGFACE_API_KEY", ""),
            patch.object(settings, "GROQ_API_KEY", ""),
        ):
            self.assertTrue(rag.embedding_available())

    def test_retrieval_is_limited_to_the_requested_judgment(self) -> None:
        with patch("app.services.rag.embed_texts", side_effect=self.fake_embeddings):
            first = rag.index_judgment(
                "The court requires written notice before contract termination.",
                filename="first.pdf",
                page_texts=[(4, "The court requires written notice before contract termination.")],
            )
            rag.index_judgment(
                "Unrelated material about another matter.",
                filename="second.pdf",
                page_texts=[(9, "Unrelated material about another matter.")],
            )

            with patch(
                "app.services.rag.llm.generate_json",
                return_value={"answer": "Written notice is required.", "supported": True, "citations": [1]},
            ) as generate:
                result = rag.answer_question(first["document_id"], "Is written notice required?")

        self.assertTrue(result["supported"])
        self.assertEqual(result["passages"][0]["page_number"], 4)
        self.assertIn("written notice", result["passages"][0]["text"].lower())
        self.assertNotIn("Unrelated material", generate.call_args.args[0])

    def test_unsupported_question_returns_insufficient_evidence_without_llm_answer(self) -> None:
        with patch("app.services.rag.embed_texts", side_effect=self.fake_embeddings):
            indexed = rag.index_judgment(
                "The court requires written notice before contract termination.",
                filename="judgment.txt",
            )
            with patch("app.services.rag.llm.generate_json") as generate:
                result = rag.answer_question(
                    indexed["document_id"], "What is the boiling point of water?"
                )

        self.assertFalse(result["supported"])
        self.assertIn("Insufficient evidence", result["answer"])
        self.assertEqual(result["passages"], [])
        generate.assert_not_called()

    def test_only_model_cited_retrieved_passages_are_returned(self) -> None:
        with patch("app.services.rag.embed_texts", side_effect=self.fake_embeddings):
            indexed = rag.index_judgment(
                "The notice must be sent to the registered address. "
                "The court held written notice is required before termination.",
                filename="judgment.txt",
                page_texts=[
                    (3, "The notice must be sent to the registered address."),
                    (7, "The court held written notice is required before termination."),
                ],
            )
            with patch(
                "app.services.rag.llm.generate_json",
                return_value={"answer": "Notice is required.", "supported": True, "citations": [2]},
            ):
                result = rag.answer_question(indexed["document_id"], "Is written notice required?")

        self.assertEqual(len(result["passages"]), 1)
        self.assertEqual(result["passages"][0]["page_number"], 7)
        self.assertIn("written notice is required", result["passages"][0]["text"])

    def test_model_unsupported_response_is_normalised_to_clear_insufficient_evidence(self) -> None:
        with patch("app.services.rag.embed_texts", side_effect=self.fake_embeddings):
            indexed = rag.index_judgment(
                "The court requires written notice before termination.",
                filename="judgment.txt",
            )
            with patch(
                "app.services.rag.llm.generate_json",
                return_value={"answer": "The excerpt does not say.", "supported": False, "citations": []},
            ):
                result = rag.answer_question(indexed["document_id"], "What happened after termination?")

        self.assertFalse(result["supported"])
        self.assertEqual(
            result["answer"],
            "Insufficient evidence in the uploaded judgment to answer this question.",
        )
        self.assertEqual(result["passages"], [])

    def test_upload_and_question_api_preserve_page_citations(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app
        from app.services.documents import Extraction

        extracted = Extraction(
            "The court requires written notice before termination.",
            "pdf-text",
            1,
            "judgment.pdf",
            page_texts=[(11, "The court requires written notice before termination.")],
        )
        with (
            patch("app.api.routes.documents.extract", return_value=extracted),
            patch("app.services.rag.embed_texts", side_effect=self.fake_embeddings),
            patch(
                "app.services.rag.llm.generate_json",
                return_value={"answer": "Written notice is required.", "supported": True, "citations": [1]},
            ),
            TestClient(app) as client,
        ):
            uploaded = client.post(
                "/api/extract",
                files={"file": ("judgment.pdf", b"pdf fixture", "application/pdf")},
                data={"index_judgment": "true"},
            )
            self.assertEqual(uploaded.status_code, 200)
            document_id = uploaded.json()["document_id"]
            answer = client.post(
                f"/api/judgments/{document_id}/questions",
                json={"question": "Is written notice required?"},
            )
            follow_up = client.post(
                f"/api/judgments/{document_id}/questions",
                json={"question": "Which page discusses the notice requirement?"},
            )
            removed = client.delete(f"/api/judgments/{document_id}")

        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json()["passages"][0]["page_number"], 11)
        self.assertEqual(follow_up.status_code, 200)
        self.assertEqual(follow_up.json()["passages"][0]["page_number"], 11)
        self.assertEqual(removed.status_code, 200)

    def test_existing_judgment_summary_still_returns_a_structured_brief(self) -> None:
        with patch(
            "app.services.analysis.llm.generate_json",
            return_value={
                "case_details": {"case_name": "A v B", "court": "Supreme Court"},
                "facts": "The parties entered a contract.",
                "held": "The appeal was dismissed.",
            },
        ):
            brief = analysis.summarise_judgment("The court dismissed the appeal.")

        self.assertEqual(brief["case_details"]["case_name"], "A v B")
        self.assertEqual(brief["facts"], "The parties entered a contract.")
        self.assertEqual(brief["outcome"], "The appeal was dismissed.")


if __name__ == "__main__":
    unittest.main()
