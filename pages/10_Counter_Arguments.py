import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="Counter Arguments", page_icon="🛡️", layout="wide")
st.title("🛡️ Counter Arguments Drafter")
st.caption("Upload opposing party's claim document → extract claims → draft counter-arguments with inline citations → assemble Written Statement.")

from core.counter_args import (
    extract_claims, draft_counter, draft_all_counters,
    assemble_written_statement, ask_about_claim,
)
from utils.pdf_utils import extract_text_auto

# Session state
if "claims" not in st.session_state:
    st.session_state.claims = []
if "counters" not in st.session_state:
    st.session_state.counters = []
if "counter_doc_text" not in st.session_state:
    st.session_state.counter_doc_text = ""

# --- Step 1: Upload ---
st.markdown("### Step 1: Upload Opposing Document")
uploaded = st.file_uploader("Upload Statement of Claims / Plaint / Written Statement", type=["pdf", "docx"])
paste = st.text_area("Or paste document text:", height=100, placeholder="Paste the opposing party's document...")

if st.button("Extract Claims", type="primary", disabled=not (uploaded or paste.strip())):
    with st.spinner("Extracting claims from document..."):
        if uploaded:
            text, _ = extract_text_auto(uploaded.read(), uploaded.name)
        else:
            text = paste
        st.session_state.counter_doc_text = text
        st.session_state.claims = extract_claims(text)
        st.session_state.counters = []

    if not st.session_state.claims:
        st.warning("No claims extracted. Try pasting the text directly or check document format.")
    else:
        st.success(f"Extracted **{len(st.session_state.claims)} claims**.")

# --- Step 2: Review Claims ---
if st.session_state.claims:
    st.markdown("---")
    st.markdown(f"### Step 2: Review Extracted Claims ({len(st.session_state.claims)})")

    strength_colors = {"STRONG": "red", "MODERATE": "orange", "WEAK": "green"}
    for c in st.session_state.claims:
        strength = c.get("strength", "MODERATE")
        color = strength_colors.get(strength, "gray")
        with st.expander(f"Claim {c['claim_id']}: {c['claim'][:80]}... [:{color}[{strength}]]"):
            st.write(f"**Claim:** {c['claim']}")
            st.write(f"**Legal Basis:** {c.get('legal_basis', '-')}")
            st.write(f"**Key Facts:** {c.get('key_facts', '-')}")
            st.write(f"**Assessed Strength:** {strength}")

    if st.button("Draft All Counter-Arguments", type="primary"):
        with st.spinner(f"Drafting counters for {len(st.session_state.claims)} claims..."):
            st.session_state.counters = draft_all_counters(st.session_state.claims)
        st.success("Counter-arguments drafted!")

# --- Step 3: Review Counters ---
if st.session_state.counters:
    st.markdown("---")
    st.markdown("### Step 3: Counter-Arguments")

    for i, c in enumerate(st.session_state.counters):
        with st.expander(f"Counter {c['claim_id']}: {c['original_claim'][:70]}..."):
            st.markdown("**Counter-Argument:**")
            st.write(c.get("counter_argument", ""))
            st.markdown(f"**Legal Basis:** {c.get('legal_basis', '-')}")

            cites = c.get("citations", [])
            if cites:
                st.markdown("**Inline Citations:**")
                for cite in cites:
                    st.markdown(f"- 📌 `{cite['source']}` — {cite['relevance']}")

            if c.get("strategy_note"):
                st.info(f"Strategy: {c['strategy_note']}")

            # Ask AI about this counter
            st.markdown("---")
            q_key = f"ask_q_{i}"
            counter_q = st.text_input("Ask AI about this claim/counter:", key=q_key)
            if st.button("Ask", key=f"ask_btn_{i}"):
                with st.spinner("Answering..."):
                    answer = ask_about_claim(counter_q, c["original_claim"], c.get("counter_argument", ""))
                st.write(answer)

    # --- Step 4: Assemble Written Statement ---
    st.markdown("---")
    st.markdown("### Step 4: Assemble Written Statement")
    col1, col2, col3 = st.columns(3)
    petitioner = col1.text_input("Petitioner / Claimant")
    respondent = col2.text_input("Respondent / Defendant")
    court = col3.text_input("Court / Forum")
    extra = st.text_area("Additional Defences (optional)", height=80)

    if st.button("Assemble Written Statement", type="primary"):
        with st.spinner("Assembling Written Statement..."):
            ws = assemble_written_statement(petitioner, respondent, court, st.session_state.counters, extra)

        st.text_area("Written Statement Draft", value=ws, height=500, label_visibility="collapsed")

        from utils.docx_utils import create_legal_document_docx
        docx_bytes = create_legal_document_docx(
            "Written Statement", ws,
            f"{petitioner} vs {respondent}", court,
        )
        st.download_button(
            "⬇️ Download Written Statement as DOCX",
            data=docx_bytes,
            file_name="written_statement_draft.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
