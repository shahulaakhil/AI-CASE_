import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="Authority Check", page_icon="✅", layout="wide")
st.title("✅ Authority Check")
st.caption("Is your cited judgment still good law? Find out if it's been overruled, distinguished, or affirmed.")

STATUS_COLORS = {
    "GOOD LAW": "green",
    "CAUTIONED": "orange",
    "DISTINGUISHED": "blue",
    "OVERRULED": "red",
    "UNKNOWN": "gray",
}

STATUS_ICONS = {
    "GOOD LAW": "✅",
    "CAUTIONED": "⚠️",
    "DISTINGUISHED": "🔵",
    "OVERRULED": "❌",
    "UNKNOWN": "❓",
}

citation = st.text_input(
    "Judgment citation or case name",
    placeholder="e.g., Maneka Gandhi vs Union of India AIR 1978 SC 597",
)

st.caption("Tip: Enter the full citation for best results. Searches Indian Kanoon for citing judgments.")

if st.button("Check Authority", type="primary", disabled=not citation.strip()):
    with st.spinner("Searching Indian Kanoon for citing judgments..."):
        from core.authority_check import check_authority
        try:
            result = check_authority(citation)
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

    if result.get("mock_note"):
        st.info(f"ℹ️ {result['mock_note']}")

    status = result.get("status", "UNKNOWN")
    confidence = result.get("confidence", "LOW")
    icon = STATUS_ICONS.get(status, "❓")
    color = STATUS_COLORS.get(status, "gray")

    # Status card
    st.markdown(f"## {icon} Status: :{color}[{status}]")
    st.markdown(f"**Confidence:** {confidence}")
    st.markdown("---")
    st.markdown("### Summary")
    st.write(result.get("summary", ""))

    # Citing cases
    citing = result.get("citing_cases", [])
    if citing:
        st.markdown("---")
        st.markdown(f"### Citing Cases ({len(citing)})")
        for c in citing:
            treatment = c.get("treatment", "")
            with st.expander(f"📄 {c.get('case_name', 'Unknown')} — {treatment}"):
                st.write(c.get("excerpt", ""))
    else:
        st.info("No citing cases found in search results.")

    st.caption(f"Searched: {result.get('citation_searched', citation)}")
