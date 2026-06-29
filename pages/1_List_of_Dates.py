import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="List of Dates", page_icon="📅", layout="wide")
st.title("📅 List of Dates Generator")
st.caption("Upload case files, pleadings, FIRs, or judgments — get a court-ready chronological table.")

uploaded = st.file_uploader(
    "Upload document (PDF or DOCX)",
    type=["pdf", "docx"],
    help="Supports digital PDFs and scanned PDFs (via Gemini Vision OCR).",
)
case_title = st.text_input("Case Title (optional)", placeholder="e.g., ABC vs XYZ — CS(OS) 123/2024")

if uploaded and st.button("Generate List of Dates", type="primary"):
    with st.spinner("Extracting dates from document..."):
        from core.list_of_dates import ocr_and_extract
        try:
            rows, method = ocr_and_extract(uploaded.read(), uploaded.name, case_title)
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

    if not rows:
        st.warning("No dates found in the document. Check that the file contains readable text.")
        st.stop()

    st.success(f"Found **{len(rows)} events** (extraction method: {method})")

    # Display as table
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=400)

    # Download buttons
    col1, col2 = st.columns(2)
    with col1:
        from utils.docx_utils import create_list_of_dates_docx
        docx_bytes = create_list_of_dates_docx(rows, case_title)
        st.download_button(
            "⬇️ Download as DOCX",
            data=docx_bytes,
            file_name=f"list_of_dates_{case_title or 'case'}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    with col2:
        csv = df.to_csv(index=False).encode()
        st.download_button(
            "⬇️ Download as CSV",
            data=csv,
            file_name=f"list_of_dates_{case_title or 'case'}.csv",
            mime="text/csv",
        )

    # Expandable raw view
    with st.expander("Raw JSON"):
        import json
        st.code(json.dumps(rows, indent=2), language="json")
