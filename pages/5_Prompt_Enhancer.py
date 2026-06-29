import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="Prompt Enhancer", page_icon="✨", layout="wide")
st.title("✨ Prompt Enhancement")
st.caption("Lawyers think in facts and disputes. This tool transforms your raw question into a structured LLM instruction for optimal AI responses.")

raw_query = st.text_area(
    "Your raw legal question",
    height=120,
    placeholder="e.g., Can my client get compensation for mental harassment caused by the builder who delayed possession?",
)

if st.button("Enhance Prompt", type="primary", disabled=not raw_query.strip()):
    with st.spinner("Enhancing your prompt..."):
        from core.prompt_enhancer import enhance_prompt
        try:
            result = enhance_prompt(raw_query)
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

    # Classification badges
    cats = result.get("categories", [])
    juris = result.get("jurisdiction", "")
    if cats:
        st.markdown("**Detected Legal Areas:** " + " · ".join(f"`{c}`" for c in cats))
    if juris:
        st.markdown(f"**Jurisdiction:** `{juris}`")

    st.markdown("---")
    st.markdown("### Enhanced Prompt")
    st.text_area("", value=result["enhanced_prompt"], height=300, label_visibility="collapsed")

    if result.get("enhancement_note"):
        st.info(f"Enhancement note: {result['enhancement_note']}")

    # Copy + send to research
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Download enhanced prompt",
            data=result["enhanced_prompt"],
            file_name="enhanced_prompt.txt",
            mime="text/plain",
        )
    with col2:
        if st.button("🔍 Send to Legal Research"):
            st.session_state["prefill_research"] = result["enhanced_prompt"]
            st.switch_page("pages/2_Legal_Research.py")
