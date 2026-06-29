import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="Judgment Summariser", page_icon="📖", layout="wide")
st.title("📖 Judgment Summariser")
st.caption("Upload any Indian court judgment and get a structured brief: Facts → Issues → Held → Ratio → Significance.")

uploaded = st.file_uploader(
    "Upload judgment (PDF or DOCX)",
    type=["pdf", "docx"],
    help="Supports digital and scanned PDFs via Gemini Vision OCR.",
)
paste_text = st.text_area(
    "Or paste judgment text directly:",
    height=120,
    placeholder="Paste the full text of the judgment here...",
)

if st.button("Summarise", type="primary", disabled=not (uploaded or paste_text.strip())):
    with st.spinner("Reading and summarising judgment..."):
        from core.judgment_summariser import ocr_and_summarise, summarise_judgment
        try:
            if uploaded:
                brief, method = ocr_and_summarise(uploaded.read(), uploaded.name)
            else:
                brief = summarise_judgment(paste_text)
                method = "paste"
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

    st.success(f"Summarised! (method: {method})")

    # Case details card
    details = brief.get("case_details", {})
    if details:
        st.markdown("### Case Details")
        cols = st.columns(3)
        cols[0].metric("Case", details.get("case_name", "-"))
        cols[1].metric("Court", details.get("court", "-"))
        cols[2].metric("Date", details.get("date_of_judgment", "-"))
        if details.get("citation"):
            st.markdown(f"**Citation:** `{details['citation']}`")
        if details.get("bench"):
            st.markdown(f"**Bench:** {details['bench']}")
        if details.get("subject_matter"):
            st.markdown(f"**Subject:** {details['subject_matter']}")

    st.markdown("---")

    sections = [
        ("Facts", "facts"),
        ("Issues Framed", "issues"),
        ("Petitioner / Appellant Arguments", "petitioner_arguments"),
        ("Respondent Arguments", "respondent_arguments"),
        ("Held", "held"),
        ("Ratio Decidendi", "ratio"),
        ("Significance", "significance"),
    ]
    for heading, key in sections:
        content = brief.get(key)
        if not content:
            continue
        st.markdown(f"### {heading}")
        if isinstance(content, list):
            for item in content:
                st.markdown(f"- {item}")
        else:
            st.write(content)

    # Statutes & cases cited
    col1, col2 = st.columns(2)
    with col1:
        statutes = brief.get("key_statutes_cited", [])
        if statutes:
            st.markdown("**Key Statutes Cited:**")
            for s in statutes:
                st.markdown(f"- {s}")
    with col2:
        cited = brief.get("key_cases_cited", [])
        if cited:
            st.markdown("**Key Cases Cited:**")
            for c in cited:
                st.markdown(f"- {c}")

    # Download
    from utils.docx_utils import create_judgment_brief_docx
    docx_bytes = create_judgment_brief_docx(brief, details.get("case_name", "Judgment"))
    st.markdown("---")
    st.download_button(
        "⬇️ Download Brief as DOCX",
        data=docx_bytes,
        file_name=f"brief_{details.get('case_name', 'judgment').replace(' ', '_')[:40]}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
