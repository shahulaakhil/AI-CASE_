import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st


# ── helpers ──────────────────────────────────────────────────────────────────

def _extract_doc_text(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, DOCX, or TXT."""
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".pdf":
            import fitz  # PyMuPDF
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            return "\n".join(page.get_text() for page in doc)
        elif ext in (".doc", ".docx"):
            from docx import Document
            from io import BytesIO
            d = Document(BytesIO(file_bytes))
            return "\n".join(p.text for p in d.paragraphs if p.text.strip())
        elif ext == ".txt":
            return file_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        return f"[Text extraction failed: {e}]"
    return ""


def _doc_qa(doc_text: str, question: str, doc_name: str, prior_qa: list[dict]) -> str:
    """Answer a question about a specific uploaded document using Gemini."""
    from core.llm import gemini_generate

    # Build conversation context from prior Q&A on the same document
    history_block = ""
    if prior_qa:
        history_block = "\nPREVIOUS Q&A ON THIS DOCUMENT:\n"
        for item in prior_qa[-4:]:  # last 4 exchanges for context
            history_block += f"Q: {item['question']}\nA: {item['answer'][:500]}…\n\n"

    truncated = doc_text[:80000]  # ~20k tokens – well within Gemini's window
    prompt = (
        f"Document name: {doc_name}\n\n"
        f"---BEGIN DOCUMENT---\n{truncated}\n---END DOCUMENT---\n"
        f"{history_block}\n"
        f"User question: {question}\n\n"
        "Instructions:\n"
        "1. Identify the EXACT paragraph numbers / page numbers that directly support "
        "or contradict the user's argument or question.\n"
        "2. Quote or closely paraphrase each relevant paragraph, prefixed with its number "
        "(e.g., Para 15 states: [exact text of the paragraph]).\n"
        "3. Label each as SUPPORTS / CONTRADICTS / CONTEXT depending on relevance.\n"
        "4. If no paragraph is relevant, clearly state 'NOT RELEVANT' and explain why.\n"
        "5. Do NOT summarise the entire document — focus only on what answers the question."
    )
    system = (
        "You are a senior Indian advocate helping find exact paragraphs in legal documents "
        "that support or contradict a specific legal argument. Be precise and cite paragraph "
        "numbers wherever possible."
    )
    return gemini_generate(prompt, system_instruction=system, temperature=0.1, max_output_tokens=3000)


# ── page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Legal Research", page_icon="🔍", layout="wide")
st.title("🔍 Legal Research Assistant")
st.caption(
    "Ask any Indian law question — get cited answers backed by case law and statutes. "
    "Upload a judgment to find the exact paragraphs that support your argument."
)

# Receive prefill from Prompt Enhancer's "Send to Legal Research" button
_prefill = st.session_state.pop("prefill_research", "")
if _prefill:
    st.info(
        "**Prompt received from Prompt Enhancer** — copy the text below and paste it in the chat input.",
        icon="💡",
    )
    st.code(_prefill, language=None)

# ── sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    max_results = st.slider("Max case results", 1, 10, 5)

    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.pop("research_history", None)
        st.session_state.pop("uploaded_doc_bytes", None)
        st.session_state.pop("uploaded_doc_name", None)
        st.rerun()

    st.markdown("---")
    with st.expander("✨ Enhance my query first"):
        raw_q = st.text_area("Enter your raw question:", height=80, key="raw_q_sidebar")
        if st.button("Enhance Prompt", key="enhance_btn"):
            if raw_q.strip():
                with st.spinner("Enhancing…"):
                    from core.prompt_enhancer import enhance_prompt
                    enhanced = enhance_prompt(raw_q)
                st.success("Enhanced!")
                st.text_area(
                    "Enhanced prompt (copy to chat below):",
                    value=enhanced["enhanced_prompt"],
                    height=130,
                    key="enhanced_result",
                )
                if enhanced.get("enhancement_note"):
                    st.info(enhanced["enhancement_note"])

# ── document upload ───────────────────────────────────────────────────────────

uploaded_doc = st.file_uploader(
    "📎 Upload a judgment or document to question (optional)",
    type=["pdf", "docx", "txt"],
    help=(
        "Upload a judgment PDF, then ask in the chat below: 'Which paragraph supports "
        "Section 73 ICA?' — the AI will locate the exact paragraphs. "
        "Leave empty for general Indian law research."
    ),
)

# Cache file bytes across re-runs (file_uploader resets on each interaction)
if uploaded_doc:
    if st.session_state.get("uploaded_doc_name") != uploaded_doc.name:
        st.session_state.uploaded_doc_bytes = uploaded_doc.read()
        st.session_state.uploaded_doc_name = uploaded_doc.name
    st.info(
        f"📄 **{uploaded_doc.name}** loaded — questions will be answered from this document."
    )
elif "uploaded_doc_name" in st.session_state:
    # File was cleared
    st.session_state.pop("uploaded_doc_bytes", None)
    st.session_state.pop("uploaded_doc_name", None)

# ── chat history ──────────────────────────────────────────────────────────────

if "research_history" not in st.session_state:
    st.session_state.research_history = []

for item in st.session_state.research_history:
    with st.chat_message("user"):
        if item.get("doc_name"):
            st.caption(f"📎 {item['doc_name']}")
        st.write(item["question"])

    with st.chat_message("assistant"):
        if item.get("mock_note"):
            st.info(f"ℹ️ {item['mock_note']}")
        st.markdown(item["answer"])
        if item.get("sources"):
            with st.expander(f"📌 Sources ({len(item['sources'])})"):
                for s in item["sources"]:
                    st.markdown(f"**[{s['n']}] {s['title']}**")
                    st.write(s.get("headline", ""))
                    if s.get("tid"):
                        st.caption(f"Indian Kanoon ID: {s['tid']}")
        if item.get("intent"):
            st.caption(f"Query intent: **{item['intent']}**")

# ── chat input (Enter to send, mobile-friendly) ───────────────────────────────

if question := st.chat_input("Ask your legal question… (press Enter to send)"):
    doc_name = st.session_state.get("uploaded_doc_name")
    doc_bytes = st.session_state.get("uploaded_doc_bytes")
    using_doc = bool(doc_name and doc_bytes)

    with st.chat_message("user"):
        if using_doc:
            st.caption(f"📎 {doc_name}")
        st.write(question)

    history_item: dict = {"question": question, "doc_name": doc_name if using_doc else None}

    with st.chat_message("assistant"):
        if using_doc:
            with st.spinner(f"Searching {doc_name}…"):
                doc_text = _extract_doc_text(doc_bytes, doc_name)
                # Pass prior Q&A about the same document for multi-turn context
                prior_doc_qa = [
                    h for h in st.session_state.research_history
                    if h.get("doc_name") == doc_name
                ]
                answer = _doc_qa(doc_text, question, doc_name, prior_doc_qa)
            history_item.update({"answer": answer, "sources": [], "intent": "DOC_QA"})
        else:
            with st.spinner("Researching Indian law…"):
                from core.legal_research import research
                try:
                    result = research(question, max_results=max_results)
                except Exception as e:
                    st.error(f"Research failed: {e}")
                    st.stop()
            history_item.update({
                "answer": result["answer"],
                "sources": result.get("sources", []),
                "mock_note": result.get("mock_note", ""),
                "intent": result.get("intent", "GENERAL"),
            })

        if history_item.get("mock_note"):
            st.info(f"ℹ️ {history_item['mock_note']}")
        st.markdown(history_item["answer"])
        if history_item.get("sources"):
            with st.expander(f"📌 Sources ({len(history_item['sources'])})"):
                for s in history_item["sources"]:
                    st.markdown(f"**[{s['n']}] {s['title']}**")
                    st.write(s.get("headline", ""))
                    if s.get("tid"):
                        st.caption(f"Indian Kanoon ID: {s['tid']}")
        if history_item.get("intent"):
            st.caption(f"Query intent: **{history_item['intent']}**")

    st.session_state.research_history.append(history_item)
