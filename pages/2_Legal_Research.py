import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="Legal Research", page_icon="🔍", layout="wide")
st.title("🔍 Legal Research Assistant")
st.caption("Ask any Indian law question — get cited answers backed by case law and statutes.")

# Prompt enhancement integration
with st.expander("✨ Enhance my query first (recommended for complex questions)"):
    raw_q = st.text_area("Enter your raw question to enhance:", height=80, key="raw_q")
    if st.button("Enhance Prompt"):
        if raw_q.strip():
            with st.spinner("Enhancing..."):
                from core.prompt_enhancer import enhance_prompt
                result = enhance_prompt(raw_q)
            st.success("Prompt enhanced!")
            st.text_area("Enhanced prompt (copy to question box below):", value=result["enhanced_prompt"], height=150)
            if result.get("enhancement_note"):
                st.info(f"Note: {result['enhancement_note']}")

prefill = st.session_state.pop("prefill_research", "")
question = st.text_area(
    "Your legal research question",
    value=prefill,
    height=120,
    placeholder="e.g., What are the grounds for granting injunction under Order 39 CPC? Cite key Supreme Court judgments.",
)

col1, col2 = st.columns([1, 3])
with col1:
    max_results = st.slider("Max case results", 1, 10, 5)

if st.button("Research", type="primary", disabled=not question.strip()):
    with st.spinner("Researching Indian law..."):
        from core.legal_research import research
        try:
            result = research(question, max_results=max_results)
        except Exception as e:
            st.error(f"Research failed: {e}")
            st.stop()

    # Show mock note if Kanoon not configured
    if result.get("mock_note"):
        st.info(f"ℹ️ {result['mock_note']}")

    st.markdown("### Answer")
    st.markdown(result["answer"])

    if result.get("sources"):
        st.markdown("---")
        st.markdown("### Sources Retrieved")
        for s in result["sources"]:
            with st.expander(f"[Source {s['n']}] {s['title']}"):
                st.write(s.get("headline", "No preview available."))
                if s.get("tid"):
                    st.caption(f"Indian Kanoon ID: {s['tid']}")
    else:
        st.caption("No case sources retrieved — answer based on general Indian legal knowledge.")

    st.caption(f"Query classified as: **{result.get('intent', 'GENERAL')}**")
