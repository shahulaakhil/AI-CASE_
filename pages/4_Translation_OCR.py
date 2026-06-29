import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="Translation + OCR", page_icon="🌐", layout="wide")
st.title("🌐 Translation + OCR + Ask AI")
st.caption("Upload any legal document in any Indian language — extract, translate, and chat with it.")

# Session state
if "doc_text" not in st.session_state:
    st.session_state.doc_text = ""
if "translated_text" not in st.session_state:
    st.session_state.translated_text = ""
if "detected_lang" not in st.session_state:
    st.session_state.detected_lang = ""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

uploaded = st.file_uploader(
    "Upload document (PDF, DOCX, PNG, JPG)",
    type=["pdf", "docx", "png", "jpg", "jpeg"],
)

col1, col2 = st.columns(2)
with col1:
    translate = st.checkbox("Translate to English", value=True)
with col2:
    if st.button("Process Document", type="primary", disabled=not uploaded):
        with st.spinner("Extracting text..."):
            from core.doc_translator import ocr_extract, detect_language, translate_to_english
            try:
                text, method = ocr_extract(uploaded.read(), uploaded.name)
                st.session_state.doc_text = text
                st.session_state.chat_history = []
                lang = detect_language(text[:500])
                st.session_state.detected_lang = lang
            except Exception as e:
                st.error(f"Extraction failed: {e}")
                st.stop()

        if translate and lang.lower() not in ("english", "en"):
            with st.spinner(f"Translating from {lang} to English..."):
                try:
                    translated = translate_to_english(text, lang)
                    st.session_state.translated_text = translated
                except Exception as e:
                    st.warning(f"Translation failed: {e}")
                    st.session_state.translated_text = ""
        else:
            st.session_state.translated_text = ""

        st.success(f"Done! Extraction method: **{method}**, Language detected: **{lang}**")

# Show extracted text
if st.session_state.doc_text:
    tab1, tab2 = st.tabs(["Original Text", "Translated Text"] if st.session_state.translated_text else ["Extracted Text"])
    with tab1:
        st.text_area("", value=st.session_state.doc_text[:5000], height=300, disabled=True,
                     label_visibility="collapsed")
        if len(st.session_state.doc_text) > 5000:
            st.caption(f"Showing first 5000 of {len(st.session_state.doc_text)} characters.")
    if st.session_state.translated_text:
        with tab2:
            st.text_area("", value=st.session_state.translated_text[:5000], height=300, disabled=True,
                         label_visibility="collapsed")

    st.markdown("---")
    st.markdown("### 💬 Ask AI About This Document")

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_q = st.chat_input("Ask a question about the document...")
    if user_q:
        st.session_state.chat_history.append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.write(user_q)
        with st.chat_message("assistant"):
            with st.spinner("Answering..."):
                from core.doc_translator import ask_document
                answer = ask_document(
                    user_q,
                    st.session_state.doc_text,
                    st.session_state.translated_text,
                )
            st.write(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
