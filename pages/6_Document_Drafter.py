import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="Document Drafter", page_icon="📝", layout="wide")
st.title("📝 Legal Document Drafter")
st.caption("Draft court-ready Indian legal documents with automatic inline citations.")

from core.doc_drafter import DOC_TYPES, draft_document, extract_citations

col1, col2 = st.columns([1, 2])
with col1:
    doc_type = st.selectbox("Document Type", DOC_TYPES)
    court = st.text_input("Court / Forum", placeholder="e.g., High Court of Delhi")

with col2:
    petitioner = st.text_input("Petitioner / Claimant", placeholder="Full name + address")
    respondent = st.text_input("Respondent / Defendant", placeholder="Full name + address")

facts = st.text_area(
    "Facts of the Case",
    height=200,
    placeholder=(
        "Describe the facts in chronological order:\n"
        "- Date of transaction / agreement\n"
        "- What went wrong\n"
        "- Losses suffered\n"
        "- Prior correspondence / notices"
    ),
)
extra = st.text_area(
    "Additional Instructions (optional)",
    height=80,
    placeholder="e.g., Include prayer for interim injunction. Emphasise breach of fiduciary duty.",
)

if st.button("Draft Document", type="primary", disabled=not facts.strip()):
    with st.spinner(f"Drafting {doc_type}..."):
        try:
            draft = draft_document(doc_type, facts, petitioner, respondent, court, extra)
        except Exception as e:
            st.error(f"Drafting failed: {e}")
            st.stop()

    st.success("Draft generated!")
    st.text_area("Draft", value=draft, height=500, label_visibility="collapsed")

    # Inline citations
    citations = extract_citations(draft)
    if citations:
        with st.expander(f"📎 Inline Citations ({len(citations)}) — verify before filing"):
            for c in citations:
                badge = "⚠️ Verify" if c["needs_verification"] else "📌"
                st.write(f"{badge} [{c['n']}] {c['citation']}")

    # Download
    from utils.docx_utils import create_legal_document_docx
    docx_bytes = create_legal_document_docx(doc_type, draft, f"{petitioner} vs {respondent}", court)
    st.download_button(
        "⬇️ Download as DOCX",
        data=docx_bytes,
        file_name=f"{doc_type.replace(' ', '_').lower()}_draft.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
