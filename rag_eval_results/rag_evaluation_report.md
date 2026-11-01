# LitigatAI RAG Evaluation

- Status: **completed**
- Questions in dataset: 15
- Questions with output rows: 15
- Documents indexed: 2
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- LLM: `groq` / `qwen/qwen3.8-27b`
- Retrieval top-k: 5

## Benchmark document mapping

| Benchmark ID | PDF |
|---|---|
| `2c909352ffc6` | `48216_2024_9_1502_63440_Judgement_19-Aug-2025.pdf` |
| `35b3c146f681` | `State_vs_Nijam_Sheik_on_18_March_2026.PDF` |

## Measured retrieval metrics

All retrieval metrics below use expected page numbers as a relevance proxy, not human-verified semantic labels.

- Eligible answerable questions: 13
- Hit Rate@5: 76.92%
- Precision@5: 24.62%
- Recall@5: 69.23%
- MRR@5: 0.4218
- Mean / median retrieval latency: 0.0185 / 0.0216 s
- Mean / median end-to-end response latency: 11.0708 / 13.463 s

## Answer quality

- Supported-flag agreement with answerability labels: 93.33% (15 answers). This is not answer correctness.
- Answer correctness, faithfulness, citation support, and hallucination are not automatically scored.
- Use `rag_manual_review.csv` to review answers against references and retrieved evidence.

## Failures

- None.

## Method and limitations

- Documents were mapped from the question/reference text and verified against PDF case captions; IDs were not treated as filename hashes.
- Temporary judgment records used a unique SQLite database under `data/rag_evaluation_isolated/`; only those records were cleaned up.
- Retrieval precision counts relevant-page chunks divided by 5; recall counts distinct expected pages retrieved divided by distinct expected pages.
- Retrieval relevance is a page-level proxy from expected_pages, not human-verified semantic relevance.
- Answer correctness, faithfulness, citation support, and hallucination require human review.
- The answerability decision agreement is not a measure of factual answer quality.
- Latency is from this local run and may differ in deployment.
