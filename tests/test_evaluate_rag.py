from __future__ import annotations

import unittest
from pathlib import Path

import evaluate_rag


class EvaluateRagTests(unittest.TestCase):
    def test_benchmark_ids_map_from_question_content_and_pdf_captions(self) -> None:
        shabuddin_pdf = Path("48216_judgment.pdf")
        nijam_pdf = Path("State_vs_Nijam_Sheikh.PDF")
        benchmark = [
            {
                "document_id": "benchmark-a",
                "question": "What was the order for Sd. Shabuddin?",
                "reference_answer": "The State of Telangana judgment acquitted the appellant.",
            },
            {
                "document_id": "benchmark-b",
                "question": "Which court decided State v. Nijam Sheikh?",
                "reference_answer": "The court acquitted Nijam Sheikh.",
            },
        ]
        pdf_pages = {
            shabuddin_pdf: [(1, "Sd. Shabuddin versus the State of Telangana.")],
            nijam_pdf: [(1, "State versus Nijam Sheikh, Tis Hazari Courts.")],
        }

        mapping = evaluate_rag.map_benchmark_documents(benchmark, pdf_pages)

        self.assertEqual(mapping, {
            "benchmark-a": shabuddin_pdf,
            "benchmark-b": nijam_pdf,
        })

    def test_mapping_rejects_multiple_pdfs_for_one_judgment(self) -> None:
        benchmark = [{
            "document_id": "benchmark-a",
            "question": "What was the order for Sd. Shabuddin?",
            "reference_answer": "State of Telangana.",
        }]
        pdf_pages = {
            Path("48216_judgment.pdf"): [(1, "Sd. Shabuddin v. State of Telangana.")],
            Path("48216_judgment_copy.pdf"): [(1, "Sd. Shabuddin v. State of Telangana.")],
        }

        with self.assertRaisesRegex(ValueError, "matched 2 PDFs"):
            evaluate_rag.map_benchmark_documents(benchmark, pdf_pages)

    def test_metrics_use_answerable_questions_and_expected_page_proxy(self) -> None:
        benchmark = [{}] * 3
        rows = [
            {
                "expected_pages": "1|2",
                "answerable_reference": True,
                "retrieval_hit_at_5_page_proxy": True,
                "precision_at_5_page_proxy": 0.2,
                "recall_at_5_page_proxy": 0.5,
                "mrr_at_5_page_proxy": 1.0,
                "model_supported_flag": True,
                "retrieval_latency_seconds": 0.1,
                "end_to_end_latency_seconds": 1.0,
            },
            {
                "expected_pages": "4",
                "answerable_reference": True,
                "retrieval_hit_at_5_page_proxy": False,
                "precision_at_5_page_proxy": 0.0,
                "recall_at_5_page_proxy": 0.0,
                "mrr_at_5_page_proxy": 0.0,
                "model_supported_flag": True,
                "retrieval_latency_seconds": 0.2,
                "end_to_end_latency_seconds": 2.0,
            },
            {
                "expected_pages": "",
                "answerable_reference": False,
                "retrieval_hit_at_5_page_proxy": "",
                "precision_at_5_page_proxy": "",
                "recall_at_5_page_proxy": "",
                "mrr_at_5_page_proxy": "",
                "model_supported_flag": False,
                "retrieval_latency_seconds": 0.3,
                "end_to_end_latency_seconds": 3.0,
            },
        ]

        summary = evaluate_rag.create_summary(
            benchmark,
            rows,
            {},
            [],
            "completed",
            "groq",
            "qwen",
        )

        metrics = summary["retrieval_metrics_expected_page_proxy"]
        self.assertEqual(metrics["eligible_answerable_questions"], 2)
        self.assertEqual(metrics["hit_rate_at_5_pct"], 50.0)
        self.assertEqual(metrics["precision_at_5_pct"], 10.0)
        self.assertEqual(metrics["recall_at_5_pct"], 25.0)
        self.assertEqual(metrics["mrr_at_5"], 0.5)


if __name__ == "__main__":
    unittest.main()
