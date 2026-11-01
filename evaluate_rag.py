"""Evaluate the existing LitigatAI RAG pipeline against the supplied benchmark.

Run from the project root with ``python evaluate_rag.py``. The evaluator uses
the application's configured embedding model and LLM provider, but writes all
temporary judgment records to a unique SQLite database under data/.
"""
from __future__ import annotations

import csv
import argparse
import json
import logging
import os
import re
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
BENCHMARK = ROOT / "rag_evaluation_questions.csv"
PDF_CANDIDATES = (
    ROOT / "48216_2024_9_1502_63440_Judgement_19-Aug-2025(1).pdf",
    ROOT / "State_vs_Nijam_Sheik_on_18_March_2026(2).PDF",
    ROOT / "48216_2024_9_1502_63440_Judgement_19-Aug-2025.pdf",
    ROOT / "State_vs_Nijam_Sheik_on_18_March_2026.PDF",
)
OUT_DIR = ROOT / "rag_eval_results"
TOP_K = 5
REQUIRED_COLUMNS = {
    "question",
    "document_id",
    "reference_answer",
    "answerable",
    "expected_pages",
}
RESULT_FIELDS = (
    "question_number",
    "question",
    "document_id",
    "pdf_filename",
    "answerable_reference",
    "reference_answer",
    "generated_answer",
    "model_supported_flag",
    "retrieved_count",
    "retrieved_pages",
    "expected_pages",
    "retrieval_hit_at_5_page_proxy",
    "precision_at_5_page_proxy",
    "recall_at_5_page_proxy",
    "mrr_at_5_page_proxy",
    "citation_pages",
    "citation_expected_page_hit_proxy",
    "retrieval_latency_seconds",
    "end_to_end_latency_seconds",
    "retrieved_passages",
    "citation_passages",
    "retrieval_error",
    "answer_error",
    "manual_correctness",
    "manual_faithfulness",
    "manual_has_unsupported_claim",
    "manual_citations_supported",
    "review_notes",
)

RUN_ID = ""
EVAL_DB_PATH = ROOT / "data" / "rag_evaluation_isolated" / "not-started.db"
LOG_PATH = OUT_DIR / "rag_evaluation_diagnostics.log"
logger = logging.getLogger("litigatai.rag_evaluation")
logger.setLevel(logging.INFO)
logger.propagate = False
logger.addHandler(logging.NullHandler())


def initialize_run() -> None:
    """Create run-specific paths and configure isolation before app imports."""
    global RUN_ID, EVAL_DB_PATH, LOG_PATH
    RUN_ID = uuid.uuid4().hex
    EVAL_DIR = ROOT / "data" / "rag_evaluation_isolated"
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DB_PATH = EVAL_DIR / f"evaluation_{RUN_ID}.db"
    LOG_PATH = OUT_DIR / "rag_evaluation_diagnostics.log"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Keep DATA_DIR on its normal location so FastEmbed can reuse the verified
    # cache; SQLITE_PATH alone selects the isolated evaluation records.
    os.environ["DATABASE_URL"] = ""
    os.environ["SQLITE_PATH"] = str(EVAL_DB_PATH)
    os.environ["DATA_DIR"] = str(ROOT / "data")

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    file_handler = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def redact_secrets(message: str) -> str:
    """Keep provider and database exceptions useful without logging credentials."""
    for key, value in os.environ.items():
        if value and any(part in key.lower() for part in ("key", "token", "secret", "password")):
            message = message.replace(value, "[REDACTED]")
    message = re.sub(
        r"(?i)(api[_ -]?key|token|password|secret)(\s*[=:]\s*)[^\s,;]+",
        r"\1\2[REDACTED]",
        message,
    )
    message = re.sub(r"\borg_[A-Za-z0-9]+\b", "[REDACTED_ORG]", message)
    return re.sub(
        r"(?i)((?:postgres(?:ql)?|mysql)://)[^@\s]+@",
        r"\1[REDACTED]@",
        message,
    )


def error_text(exc: Exception) -> str:
    return redact_secrets(f"{type(exc).__name__}: {exc}")


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def parse_pages(value: Any) -> set[int]:
    pages: set[int] = set()
    for part in safe_str(value).split("|"):
        part = part.strip()
        if part:
            try:
                pages.add(int(float(part)))
            except ValueError:
                logger.warning("Ignoring invalid expected page value %r.", part)
    return pages


def read_pdf_pages(path: Path, pymupdf: Any) -> list[tuple[int, str]]:
    with pymupdf.open(path) as document:
        pages = [
            (index + 1, page.get_text("text").strip())
            for index, page in enumerate(document)
        ]
    readable = [(page, text) for page, text in pages if text]
    if not readable:
        raise ValueError(f"No extractable text found in {path.name}; OCR is required.")
    return readable


def map_benchmark_documents(
    benchmark: list[dict[str, str]],
    pdf_pages: dict[Path, list[tuple[int, str]]],
) -> dict[str, Path]:
    """Match benchmark IDs using the question group and verify each PDF caption."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in benchmark:
        grouped.setdefault(row["document_id"].strip(), []).append(row)

    mappings: dict[str, Path] = {}
    assigned: set[Path] = set()
    for document_id, rows in grouped.items():
        metadata = " ".join(
            f"{row['question']} {row['reference_answer']}" for row in rows
        ).casefold()
        is_shabuddin = "shabuddin" in metadata or "telangana" in metadata
        is_nijam = "nijam" in metadata or "sheikh" in metadata
        if is_shabuddin == is_nijam:
            raise ValueError(
                f"Benchmark ID {document_id!r} does not identify exactly one "
                "supported judgment in its question/reference text."
            )

        if is_shabuddin:
            candidates = [
                path for path in pdf_pages
                if "48216" in path.name.casefold() or "shabuddin" in path.name.casefold()
            ]
            identity_terms = ("shabuddin", "telangana")
        else:
            candidates = [
                path for path in pdf_pages
                if "nijam" in path.name.casefold() or "sheik" in path.name.casefold()
            ]
            identity_terms = ("nijam", "sheikh")

        candidates = [
            path for path in candidates
            if identity_terms[0] in "\n".join(text for _, text in pdf_pages[path][:3]).casefold()
            and identity_terms[1] in "\n".join(text for _, text in pdf_pages[path][:3]).casefold()
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"Benchmark ID {document_id!r} matched {len(candidates)} PDFs "
                f"after checking its judgment caption: {[p.name for p in candidates]}"
            )
        path = candidates[0]
        if path in assigned:
            raise ValueError(
                f"More than one benchmark ID maps to {path.name}; refusing an ambiguous mapping."
            )
        mappings[document_id] = path
        assigned.add(path)

    if len(mappings) != len(grouped) or len(assigned) != len(mappings):
        raise ValueError("Benchmark IDs do not map one-to-one to judgment PDFs.")
    return mappings


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_resumable_rows(path: Path, benchmark: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Load prior rows only when question numbers, IDs, and question text still match."""
    if not path.is_file():
        raise FileNotFoundError(f"Cannot resume: prior results not found at {path}")
    expected = {
        index: row for index, row in enumerate(benchmark, start=1)
    }
    loaded: list[dict[str, Any]] = []
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        for saved in csv.DictReader(file):
            try:
                number = int(saved.get("question_number", ""))
            except ValueError:
                continue
            current = expected.get(number)
            if (
                current is None
                or saved.get("document_id") != current["document_id"]
                or saved.get("question") != current["question"]
            ):
                continue
            row: dict[str, Any] = dict(saved)
            row["question_number"] = number
            row["answerable_reference"] = parse_bool(row.get("answerable_reference"))
            for name in ("model_supported_flag", "retrieval_hit_at_5_page_proxy",
                         "citation_expected_page_hit_proxy"):
                value = safe_str(row.get(name)).strip().lower()
                row[name] = True if value == "true" else False if value == "false" else ""
            for name in ("retrieved_count",):
                try:
                    row[name] = int(row[name])
                except (KeyError, TypeError, ValueError):
                    row[name] = 0
            for name in (
                "precision_at_5_page_proxy",
                "recall_at_5_page_proxy",
                "mrr_at_5_page_proxy",
                "retrieval_latency_seconds",
                "end_to_end_latency_seconds",
            ):
                value = safe_str(row.get(name)).strip()
                try:
                    row[name] = float(value) if value else ""
                except ValueError:
                    row[name] = ""
            loaded.append(row)
    return sorted(loaded, key=lambda row: row["question_number"])


def build_review_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "question_number": row.get("question_number", ""),
            "document_id": row.get("document_id", ""),
            "question": row.get("question", ""),
            "reference_answer": row.get("reference_answer", ""),
            "generated_answer": row.get("generated_answer", ""),
            "retrieved_passages": row.get("retrieved_passages", "[]"),
            "citation_passages": row.get("citation_passages", "[]"),
            "human_correctness_rating": "",
            "human_faithfulness_rating": "",
            "human_hallucination_assessment": "",
            "review_notes": "",
        }
        for row in rows
    ]


def numeric_stats(values: list[float]) -> dict[str, float | None]:
    return {
        "mean_seconds": round(statistics.mean(values), 4) if values else None,
        "median_seconds": round(statistics.median(values), 4) if values else None,
    }


def create_summary(
    benchmark: list[dict[str, str]],
    rows: list[dict[str, Any]],
    mappings: dict[str, Path],
    failures: list[dict[str, Any]],
    status: str,
    provider: str,
    model: str,
) -> dict[str, Any]:
    answerable_rows = [
        row for row in rows
        if row.get("expected_pages")
        and parse_bool(row.get("answerable_reference"))
        and not row.get("retrieval_error")
    ]
    hits = [
        bool(row.get("retrieval_hit_at_5_page_proxy"))
        for row in answerable_rows
    ]
    precisions = [float(row["precision_at_5_page_proxy"]) for row in answerable_rows]
    recalls = [float(row["recall_at_5_page_proxy"]) for row in answerable_rows]
    reciprocal_ranks = [float(row["mrr_at_5_page_proxy"]) for row in answerable_rows]
    decisions = [
        row for row in rows
        if isinstance(row.get("model_supported_flag"), bool)
    ]
    decision_accuracy = (
        sum(row["model_supported_flag"] == bool(row["answerable_reference"]) for row in decisions)
        / len(decisions)
        if decisions else None
    )
    retrieval_latencies = [
        float(row["retrieval_latency_seconds"])
        for row in rows if row.get("retrieval_latency_seconds") not in ("", None)
    ]
    response_latencies = [
        float(row["end_to_end_latency_seconds"])
        for row in rows if row.get("end_to_end_latency_seconds") not in ("", None)
    ]
    return {
        "status": status,
        "dataset_questions": len(benchmark),
        "questions_with_results": len(rows),
        "questions_with_generated_answers": sum(
            bool(row.get("generated_answer")) and not row.get("answer_error") for row in rows
        ),
        "documents_evaluated": len(mappings),
        "document_mapping": {
            document_id: path.name for document_id, path in mappings.items()
        },
        "top_k": TOP_K,
        "embedding_model": "See configured application setting; verified at run time.",
        "llm_provider": provider or None,
        "llm_model": model or None,
        "retrieval_metrics_expected_page_proxy": {
            "eligible_answerable_questions": len(answerable_rows),
            "hit_rate_at_5_pct": round(100 * statistics.mean(hits), 2) if hits else None,
            "precision_at_5_pct": round(100 * statistics.mean(precisions), 2) if precisions else None,
            "recall_at_5_pct": round(100 * statistics.mean(recalls), 2) if recalls else None,
            "mrr_at_5": round(statistics.mean(reciprocal_ranks), 4) if reciprocal_ranks else None,
            "definition": (
                "Expected page membership is used as a relevance proxy. Precision counts "
                "retrieved chunks whose page is labeled relevant, divided by 5; recall is "
                "the fraction of distinct expected pages represented in the top 5."
            ),
        },
        "answerability_decision_agreement": {
            "eligible_answers": len(decisions),
            "accuracy_pct": round(100 * decision_accuracy, 2) if decision_accuracy is not None else None,
            "definition": (
                "Agreement between the model's supported flag and the CSV answerable label; "
                "not a semantic answer-correctness or faithfulness score."
            ),
        },
        "latency": {
            "retrieval": numeric_stats(retrieval_latencies),
            "end_to_end_response": numeric_stats(response_latencies),
        },
        "failures": failures,
        "limitations": [
            "Retrieval relevance is a page-level proxy from expected_pages, not human-verified semantic relevance.",
            "Answer correctness, faithfulness, citation support, and hallucination require human review.",
            "The answerability decision agreement is not a measure of factual answer quality.",
            "Latency is from this local run and may differ in deployment.",
        ],
        "production_database_modified": False,
    }


def write_reports(
    benchmark: list[dict[str, str]],
    rows: list[dict[str, Any]],
    mappings: dict[str, Path],
    failures: list[dict[str, Any]],
    status: str,
    provider: str,
    model: str,
    embedding_model: str,
) -> dict[str, Any]:
    results_path = OUT_DIR / "rag_per_question_results.csv"
    summary_path = OUT_DIR / "rag_evaluation_summary.json"
    report_path = OUT_DIR / "rag_evaluation_report.md"
    review_path = OUT_DIR / "rag_manual_review.csv"

    write_csv(results_path, RESULT_FIELDS, rows)
    review_fields = (
        "question_number", "document_id", "question", "reference_answer",
        "generated_answer", "retrieved_passages", "citation_passages",
        "human_correctness_rating", "human_faithfulness_rating",
        "human_hallucination_assessment", "review_notes",
    )
    write_csv(review_path, review_fields, build_review_rows(rows))
    summary = create_summary(benchmark, rows, mappings, failures, status, provider, model)
    summary["embedding_model"] = embedding_model or None
    summary["output_files"] = {
        "per_question_results": str(results_path),
        "manual_review": str(review_path),
        "summary": str(summary_path),
        "report": str(report_path),
        "diagnostics": str(LOG_PATH),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    metrics = summary["retrieval_metrics_expected_page_proxy"]
    latency = summary["latency"]
    failure_lines = [
        f"- Q{failure['question_number']}: {failure['question']} — {failure['message']}"
        if failure.get("question_number")
        else f"- {failure['phase']}: {failure['message']}"
        for failure in failures
    ]
    report = [
        "# LitigatAI RAG Evaluation",
        "",
        f"- Status: **{status}**",
        f"- Questions in dataset: {len(benchmark)}",
        f"- Questions with output rows: {len(rows)}",
        f"- Documents indexed: {len(mappings)}",
        f"- Embedding model: `{embedding_model or 'not loaded'}`",
        f"- LLM: `{provider or 'not configured'}` / `{model or 'not configured'}`",
        f"- Retrieval top-k: {TOP_K}",
        "",
        "## Benchmark document mapping",
        "",
        "| Benchmark ID | PDF |",
        "|---|---|",
        *[
            f"| `{document_id}` | `{path.name}` |"
            for document_id, path in mappings.items()
        ],
        "",
        "## Measured retrieval metrics",
        "",
        "All retrieval metrics below use expected page numbers as a relevance proxy, not human-verified semantic labels.",
        "",
        f"- Eligible answerable questions: {metrics['eligible_answerable_questions']}",
        f"- Hit Rate@5: {metrics['hit_rate_at_5_pct']}%",
        f"- Precision@5: {metrics['precision_at_5_pct']}%",
        f"- Recall@5: {metrics['recall_at_5_pct']}%",
        f"- MRR@5: {metrics['mrr_at_5']}",
        f"- Mean / median retrieval latency: {latency['retrieval']['mean_seconds']} / {latency['retrieval']['median_seconds']} s",
        f"- Mean / median end-to-end response latency: {latency['end_to_end_response']['mean_seconds']} / {latency['end_to_end_response']['median_seconds']} s",
        "",
        "## Answer quality",
        "",
        f"- Supported-flag agreement with answerability labels: {summary['answerability_decision_agreement']['accuracy_pct']}% "
        f"({summary['answerability_decision_agreement']['eligible_answers']} answers). This is not answer correctness.",
        "- Answer correctness, faithfulness, citation support, and hallucination are not automatically scored.",
        "- Use `rag_manual_review.csv` to review answers against references and retrieved evidence.",
        "",
        "## Failures",
        "",
        *(failure_lines or ["- None."]),
        "",
        "## Method and limitations",
        "",
        "- Documents were mapped from the question/reference text and verified against PDF case captions; IDs were not treated as filename hashes.",
        "- Temporary judgment records used a unique SQLite database under `data/rag_evaluation_isolated/`; only those records were cleaned up.",
        "- Retrieval precision counts relevant-page chunks divided by 5; recall counts distinct expected pages retrieved divided by distinct expected pages.",
        *[f"- {limitation}" for limitation in summary["limitations"]],
        "",
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")
    return summary


def main() -> int:
    initialize_run()
    parser = argparse.ArgumentParser(description="Run the LitigatAI RAG benchmark.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse successful rows from rag_eval_results/rag_per_question_results.csv and retry incomplete questions.",
    )
    args = parser.parse_args()

    benchmark: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    mappings: dict[str, Path] = {}
    failures: list[dict[str, Any]] = []
    temp_ids: list[str] = []
    provider_id = ""
    model_id = ""
    embedding_model_name = ""
    status = "failed"
    db_module: Any = None
    settings_module: Any = None
    model_loaded = False
    cleanup_failed = False

    def add_failure(
        phase: str,
        message: str,
        *,
        question_number: int | None = None,
        question: str = "",
    ) -> None:
        failure = {
            "phase": phase,
            "question_number": question_number,
            "question": question,
            "message": redact_secrets(message),
        }
        failures.append(failure)
        logger.error(
            "%s%s: %s",
            f"Q{question_number} " if question_number else "",
            phase,
            failure["message"],
        )

    logger.info("LitigatAI RAG evaluation starting (run %s).", RUN_ID)
    logger.info("Evaluation SQLite database: %s", EVAL_DB_PATH.resolve())
    logger.info("Normal application database is not selected for this run.")

    try:
        if not BENCHMARK.is_file():
            raise FileNotFoundError(f"Benchmark CSV not found: {BENCHMARK}")
        with BENCHMARK.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            columns = set(reader.fieldnames or [])
            missing = REQUIRED_COLUMNS - columns
            if missing:
                raise ValueError(f"Benchmark CSV is missing columns: {sorted(missing)}")
            benchmark = [
                {key: safe_str(value).strip() for key, value in row.items()}
                for row in reader
            ]
        if not benchmark:
            raise ValueError("Benchmark CSV contains no questions.")
        if any(not row["question"] or not row["document_id"] for row in benchmark):
            raise ValueError("Every benchmark row must have a question and document_id.")
        logger.info("Validated %d benchmark questions.", len(benchmark))
        if args.resume:
            rows = load_resumable_rows(OUT_DIR / "rag_per_question_results.csv", benchmark)
            logger.info("Loaded %d prior result rows for resume.", len(rows))

        pdfs = list(dict.fromkeys(path.resolve() for path in PDF_CANDIDATES if path.is_file()))
        logger.info("PDF files discovered:")
        for path in pdfs:
            logger.info("  %s", path.name)
        if len(pdfs) < 2:
            raise FileNotFoundError(
                f"Expected both judgment PDFs; found {len(pdfs)}: {[path.name for path in pdfs]}"
            )

        import pymupdf

        pdf_pages = {path: read_pdf_pages(path, pymupdf) for path in pdfs}
        mappings = map_benchmark_documents(benchmark, pdf_pages)
        logger.info("Verified benchmark ID to judgment mapping:")
        for document_id, path in mappings.items():
            logger.info("  %s -> %s", document_id, path.name)

        from app import db as db_module
        from app import settings as settings_module
        from app.llm import registry as llm
        from app.services import rag

        embedding_model_name = settings_module.EMBEDDING_MODEL
        if settings_module.DATABASE_URL:
            raise RuntimeError("Database isolation failed: DATABASE_URL is configured.")
        if db_module.uses_postgres():
            raise RuntimeError("Database isolation failed: evaluator selected PostgreSQL.")
        if settings_module.SQLITE_PATH.resolve() != EVAL_DB_PATH.resolve():
            raise RuntimeError("Database isolation failed: SQLite path differs from the unique evaluation path.")
        if settings_module.SQLITE_PATH.resolve() == (ROOT / "data" / "litigatai.db").resolve():
            raise RuntimeError("Database isolation failed: refusing to use the normal application database.")
        if db_module._initialised:
            raise RuntimeError("Application database was initialized before evaluation isolation.")
        logger.info("Database isolation verified: SQLite only; path=%s", settings_module.SQLITE_PATH.resolve())

        cache_dir = settings_module.DATA_DIR / "models" / "fastembed"
        cached_model = any(cache_dir.glob("models--*all-MiniLM-L6-v2*/snapshots/*/model.onnx"))
        logger.info(
            "Embedding model: %s; cache directory: %s; local model file found: %s",
            embedding_model_name,
            cache_dir.resolve(),
            cached_model,
        )
        embedding_error = None
        for attempt in range(1, 4):
            try:
                vector = rag.embed_texts(["LitigatAI RAG evaluation embedding smoke test"])[0]
                logger.info("Embedding model ready: dimension=%d.", len(vector))
                model_loaded = True
                break
            except Exception as exc:
                embedding_error = error_text(exc)
                logger.warning("Embedding initialization attempt %d/3 failed: %s", attempt, embedding_error)
                if attempt < 3:
                    time.sleep(attempt)
        if not model_loaded:
            raise RuntimeError(
                f"Could not initialize configured embedding model {embedding_model_name!r} "
                f"from cache {cache_dir.resolve()} after 3 attempts. {embedding_error}"
            )

        provider_id, model_id = llm.default_selection()
        if provider_id and model_id:
            logger.info("LLM selection from existing provider registry: %s / %s", provider_id, model_id)
        else:
            logger.error(
                "No server-side LLM provider is configured. Retrieval will still run; "
                "answer generation will be recorded as unavailable."
            )

        local_ids: dict[str, str] = {}
        for benchmark_id, pdf_path in mappings.items():
            try:
                page_texts = pdf_pages[pdf_path]
                full_text = "\n\n".join(text for _, text in page_texts)
                logger.info(
                    "Indexing %s: %d readable pages, %d characters.",
                    pdf_path.name,
                    len(page_texts),
                    len(full_text),
                )
                indexed = rag.index_judgment(
                    full_text,
                    filename=pdf_path.name,
                    page_texts=page_texts,
                )
                if not isinstance(indexed, dict) or not indexed.get("document_id"):
                    raise TypeError("rag.index_judgment() did not return a document_id.")
                local_id = str(indexed["document_id"])
                temp_ids.append(local_id)
                document = db_module.judgment(local_id)
                chunks = db_module.judgment_chunks(local_id)
                if (
                    not document
                    or document["filename"] != pdf_path.name
                    or not chunks
                    or indexed.get("chunks") != len(chunks)
                ):
                    raise RuntimeError("Indexed judgment failed database metadata/chunk validation.")
                local_ids[benchmark_id] = local_id
                logger.info(
                    "Index verified for benchmark ID %s: %d chunks.",
                    benchmark_id,
                    len(chunks),
                )
            except Exception as exc:
                add_failure("indexing", error_text(exc))

        for index, item in enumerate(benchmark, start=1):
            question = item["question"]
            benchmark_id = item["document_id"]
            previous = next(
                (row for row in rows if int(row["question_number"]) == index),
                None,
            )
            if (
                previous is not None
                and not previous.get("retrieval_error")
                and not previous.get("answer_error")
            ):
                logger.info("Q%d already succeeded; preserving prior output.", index)
                continue
            if benchmark_id not in local_ids:
                message = "Document was not indexed; see indexing diagnostic."
                add_failure("question", message, question_number=index, question=question)
                rows.append({
                    "question_number": index,
                    "question": question,
                    "document_id": benchmark_id,
                    "pdf_filename": mappings.get(benchmark_id, Path("")).name,
                    "answerable_reference": parse_bool(item["answerable"]),
                    "reference_answer": item["reference_answer"],
                    "generated_answer": "",
                    "model_supported_flag": "",
                    "retrieved_count": 0,
                    "retrieved_pages": "",
                    "expected_pages": "|".join(map(str, sorted(parse_pages(item["expected_pages"])))),
                    "retrieval_hit_at_5_page_proxy": "",
                    "precision_at_5_page_proxy": "",
                    "recall_at_5_page_proxy": "",
                    "mrr_at_5_page_proxy": "",
                    "citation_pages": "",
                    "citation_expected_page_hit_proxy": "",
                    "retrieval_latency_seconds": "",
                    "end_to_end_latency_seconds": "",
                    "retrieved_passages": "[]",
                    "citation_passages": "[]",
                    "retrieval_error": message,
                    "answer_error": message,
                })
                rows.sort(key=lambda row: int(row["question_number"]))
                write_csv(OUT_DIR / "rag_per_question_results.csv", RESULT_FIELDS, rows)
                continue

            expected_pages = parse_pages(item["expected_pages"])
            pdf_path = mappings[benchmark_id]
            local_id = local_ids[benchmark_id]
            logger.info("Q%d/%d: %s", index, len(benchmark), question)
            retrieved: list[dict[str, Any]] = []
            retrieval_error = ""
            answer_error = ""
            response: dict[str, Any] = {}
            retrieval_seconds: float | None = None
            started = time.perf_counter()
            try:
                retrieval_started = time.perf_counter()
                retrieved = rag.retrieve(local_id, question, limit=TOP_K)
                retrieval_seconds = time.perf_counter() - retrieval_started
            except Exception as exc:
                retrieval_error = error_text(exc)
                add_failure("retrieval", retrieval_error, question_number=index, question=question)

            if provider_id and model_id:
                for attempt in range(1, 4):
                    try:
                        response = rag.answer_question(
                            local_id,
                            question,
                            provider=provider_id,
                            model=model_id,
                        )
                        if not isinstance(response, dict):
                            raise TypeError("rag.answer_question() did not return a dictionary.")
                        answer_error = ""
                        break
                    except Exception as exc:
                        answer_error = error_text(exc)
                        retry_after = re.search(
                            r"try again in ([0-9.]+)\s*s",
                            str(exc),
                            re.IGNORECASE,
                        )
                        rate_limited = "429" in str(exc) or "rate limit" in str(exc).casefold()
                        if rate_limited and attempt < 3:
                            delay = min(max(float(retry_after.group(1)), 1.0), 30.0) if retry_after else 5.0
                            logger.warning(
                                "Q%d received a provider rate limit; retrying attempt %d/3 in %.1fs.",
                                index,
                                attempt + 1,
                                delay,
                            )
                            time.sleep(delay)
                            continue
                        add_failure(
                            "answer_generation",
                            answer_error,
                            question_number=index,
                            question=question,
                        )
                        break
            else:
                answer_error = "No server-side LLM provider/model is configured."
                add_failure("answer_generation", answer_error, question_number=index, question=question)
            end_to_end_seconds = time.perf_counter() - started

            retrieved_pages = [
                passage.get("page_number") for passage in retrieved
                if passage.get("page_number") is not None
            ]
            relevant_flags = [page in expected_pages for page in retrieved_pages]
            hit = bool(any(relevant_flags)) if expected_pages and not retrieval_error else ""
            precision = sum(relevant_flags) / TOP_K if expected_pages and not retrieval_error else ""
            recall = (
                len(set(retrieved_pages) & expected_pages) / len(expected_pages)
                if expected_pages and not retrieval_error else ""
            )
            first_relevant_rank = next(
                (rank for rank, is_relevant in enumerate(relevant_flags, start=1) if is_relevant),
                None,
            )
            mrr = (
                1 / first_relevant_rank
                if first_relevant_rank and expected_pages and not retrieval_error
                else (0.0 if expected_pages and not retrieval_error else "")
            )
            citations = response.get("passages") or []
            if not isinstance(citations, list):
                citations = []
            citation_pages = [
                passage.get("page_number") for passage in citations
                if isinstance(passage, dict) and passage.get("page_number") is not None
            ]
            supported = response.get("supported")
            row = {
                "question_number": index,
                "question": question,
                "document_id": benchmark_id,
                "pdf_filename": pdf_path.name,
                "answerable_reference": parse_bool(item["answerable"]),
                "reference_answer": item["reference_answer"],
                "generated_answer": safe_str(response.get("answer")),
                "model_supported_flag": supported if isinstance(supported, bool) else "",
                "retrieved_count": len(retrieved),
                "retrieved_pages": "|".join(map(str, retrieved_pages)),
                "expected_pages": "|".join(map(str, sorted(expected_pages))),
                "retrieval_hit_at_5_page_proxy": hit,
                "precision_at_5_page_proxy": round(precision, 4) if precision != "" else "",
                "recall_at_5_page_proxy": round(recall, 4) if recall != "" else "",
                "mrr_at_5_page_proxy": round(mrr, 4) if mrr != "" else "",
                "citation_pages": "|".join(map(str, citation_pages)),
                "citation_expected_page_hit_proxy": (
                    any(page in expected_pages for page in citation_pages)
                    if expected_pages else ""
                ),
                "retrieval_latency_seconds": (
                    round(retrieval_seconds, 4) if retrieval_seconds is not None else ""
                ),
                "end_to_end_latency_seconds": round(end_to_end_seconds, 4),
                "retrieved_passages": json.dumps(retrieved, ensure_ascii=False),
                "citation_passages": json.dumps(citations, ensure_ascii=False),
                "retrieval_error": retrieval_error,
                "answer_error": answer_error,
            }
            rows = [saved for saved in rows if int(saved["question_number"]) != index]
            rows.append(row)
            rows.sort(key=lambda saved: int(saved["question_number"]))
            write_csv(OUT_DIR / "rag_per_question_results.csv", RESULT_FIELDS, rows)
            logger.info(
                "Q%d completed: retrieved=%d, retrieval=%.3fs, end-to-end=%.3fs, answer=%s",
                index,
                len(retrieved),
                retrieval_seconds if retrieval_seconds is not None else 0,
                end_to_end_seconds,
                "error" if answer_error else "ok",
            )

        status = (
            "completed"
            if len(rows) == len(benchmark)
            and not failures
            and all(not row.get("retrieval_error") and not row.get("answer_error") for row in rows)
            else "incomplete"
        )
    except Exception as exc:
        message = error_text(exc)
        add_failure("setup_or_evaluation", message)
        status = "incomplete"
        logger.error("Evaluation stopped before completing the benchmark: %s", message)
    finally:
        if db_module is not None:
            for document_id in temp_ids:
                try:
                    if not db_module.delete_judgment(document_id):
                        cleanup_failed = True
                        add_failure("cleanup", f"Temporary document {document_id} was not found for deletion.")
                    else:
                        logger.info("Removed temporary evaluation document %s.", document_id)
                except Exception as exc:
                    cleanup_failed = True
                    add_failure("cleanup", error_text(exc))

        # A unique, run-owned SQLite file can be removed after its temporary
        # records are deleted; no application database or prior run is touched.
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{EVAL_DB_PATH}{suffix}")
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                cleanup_failed = True
                add_failure("cleanup", f"Could not remove run-owned database file: {error_text(exc)}")

        existing_numbers = {int(row["question_number"]) for row in rows}
        for index, item in enumerate(benchmark, start=1):
            if index not in existing_numbers:
                message = "Question was not run because evaluation setup or an earlier step failed."
                rows.append({
                    "question_number": index,
                    "question": item["question"],
                    "document_id": item["document_id"],
                    "pdf_filename": mappings.get(item["document_id"], Path("")).name,
                    "answerable_reference": parse_bool(item["answerable"]),
                    "reference_answer": item["reference_answer"],
                    "generated_answer": "",
                    "model_supported_flag": "",
                    "retrieved_count": 0,
                    "retrieved_pages": "",
                    "expected_pages": "|".join(map(str, sorted(parse_pages(item["expected_pages"])))),
                    "retrieval_hit_at_5_page_proxy": "",
                    "precision_at_5_page_proxy": "",
                    "recall_at_5_page_proxy": "",
                    "mrr_at_5_page_proxy": "",
                    "citation_pages": "",
                    "citation_expected_page_hit_proxy": "",
                    "retrieval_latency_seconds": "",
                    "end_to_end_latency_seconds": "",
                    "retrieved_passages": "[]",
                    "citation_passages": "[]",
                    "retrieval_error": message,
                    "answer_error": message,
                })
        rows.sort(key=lambda row: int(row["question_number"]))
        if cleanup_failed:
            status = "incomplete"
        try:
            summary = write_reports(
                benchmark,
                rows,
                mappings,
                failures,
                status,
                provider_id,
                model_id,
                embedding_model_name,
            )
            logger.info("Evaluation status: %s", status)
            logger.info(
                "Completed output rows: %d/%d.",
                summary["questions_with_results"],
                summary["dataset_questions"],
            )
            logger.info("Report files: %s", json.dumps(summary["output_files"], ensure_ascii=False))
            logger.info("Retrieval proxy metrics: %s", json.dumps(summary["retrieval_metrics_expected_page_proxy"]))
        except Exception as exc:
            logger.error("Could not write evaluation reports: %s", error_text(exc))
            status = "incomplete"

    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
