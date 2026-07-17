import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

st.set_page_config(
    page_title="LitigatAI — Indian Litigation AI Platform",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚖️ LitigatAI")
st.subheader("AI-Powered Litigation & Dispute Resolution Platform for Indian Advocates")
st.caption("Built for practising lawyers and litigation interns. All 10 tools in one place.")

st.markdown("---")

tools = [
    ("📆", "List of Dates", "Extract all material dates from case files into a court-ready chronological table.", "pages/1_List_of_Dates.py"),
    ("🔍", "Legal Research", "Ask Indian law questions in a continuous chat. Upload a judgment to find exact supporting paragraphs.", "pages/2_Legal_Research.py"),
    ("✅", "Authority Check", "Verify if a cited judgment is still good law — overruled, distinguished, or affirmed.", "pages/3_Authority_Check.py"),
    ("🌐", "Translation + OCR", "Extract, translate (any Indian language → English), and chat with any legal document.", "pages/4_Translation_OCR.py"),
    ("💡", "Prompt Enhancer", "Transform your raw legal question into a structured AI prompt for better research.", "pages/5_Prompt_Enhancer.py"),
    ("📋", "Document Drafter", "Draft Suits, Claims, Written Statements, Rejoinders with professional inline citations.", "pages/6_Document_Drafter.py"),
    ("🏛️", "Court Tracker", "Track all cases, hearing dates, and status — with eCourts integration.", "pages/7_Court_Tracker.py"),
    ("📑", "Judgment Summariser", "Upload any judgment → get structured brief: Facts, Issues, Held, Ratio, Significance.", "pages/8_Judgment_Summariser.py"),
    ("📖", "Bare Acts", "Browse Indian legislation, view sections with amendment history, and Ask AI about any provision.", "pages/9_Bare_Acts.py"),
    ("🛡️", "Counter Arguments", "Extract claims from opponent's document, draft counter-arguments, assemble Written Statement.", "pages/10_Counter_Arguments.py"),
]

cols = st.columns(2)
for i, (icon, name, desc, path) in enumerate(tools):
    with cols[i % 2]:
        st.markdown(f"#### {icon} {name}")
        st.write(desc)
        st.page_link(path, label=f"Open {name} →")
        st.markdown("---")

st.markdown("### Quick Links")
st.markdown("""
- Use the **sidebar** to navigate directly to any tool.
- Tools share the same Gemini + Groq backend.
- Set your `GOOGLE_API_KEY` and `GROQ_API_KEY` in `.env` before starting.
- Optional: set `INDIAN_KANOON_API_TOKEN` for live case law search (Authority Check + Legal Research).
""")

from core.court_tracker import get_upcoming_dates
upcoming = get_upcoming_dates(7)
if upcoming:
    st.markdown("---")
    st.markdown("### 🔔 Upcoming Hearings (Next 7 Days)")
    for u in upcoming:
        days = u["days_away"]
        label = "TODAY" if days == 0 else f"in {days} day(s)"
        color = "red" if days <= 2 else "orange"
        st.markdown(f":{color}[**{u['next_date']}** ({label})] — {u['case_name']} @ {u.get('court', '-')}")
