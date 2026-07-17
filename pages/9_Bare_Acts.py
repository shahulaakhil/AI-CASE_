import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="Bare Acts", page_icon="📖", layout="wide")
st.title("📖 Bare Acts & Amendments Tracker")
st.caption("Browse Indian legislation, view sections with amendment history, and Ask AI about any provision.")

from core.bare_acts import list_acts, get_act_sections, search_sections, ask_provision, get_amendments_for_act

tab1, tab2, tab3 = st.tabs(["🗂️ Browse Acts", "🔎 Search Sections", "💬 Ask AI About a Provision"])

with tab1:
    acts = list_acts()
    if not acts:
        st.warning("No acts in the local database yet. See data/bare_acts_data.json to add acts.")
    else:
        # Category filter
        categories = sorted(set(a.get("category", "Other") for a in acts))
        selected_cat = st.selectbox("Filter by category", ["All"] + categories)
        filtered = acts if selected_cat == "All" else [a for a in acts if a.get("category") == selected_cat]

        for act in filtered:
            with st.expander(f"📜 {act['name']} ({act.get('year', '')})"):
                st.write(act.get("description", ""))
                sections = get_act_sections(act["name"])
                if sections:
                    st.markdown(f"**{len(sections)} sections available:**")
                    for sec in sections:
                        has_amendments = bool(sec.get("amendments"))
                        badge = "🔴" if has_amendments else ""
                        sec_label = f"{badge} **Section {sec['section']}** — {sec.get('title', '')}"
                        with st.expander(sec_label):
                            st.write(sec.get("text", ""))
                            if has_amendments:
                                st.markdown("**Amendment History:**")
                                for am in sec["amendments"]:
                                    st.markdown(
                                        f"- **{am.get('year', '?')}**: {am.get('description', '')} "
                                        f"(Act {am.get('amending_act', '')})"
                                    )

                amendments = get_amendments_for_act(act["name"])
                if amendments:
                    st.markdown("**Act-level Amendments:**")
                    for am in amendments:
                        st.markdown(f"- **{am.get('year', '?')}**: {am.get('description', '')}")

with tab2:
    query = st.text_input("Search keyword across all acts:", placeholder="e.g., limitation, injunction, consumer")
    if query:
        results = search_sections(query)
        if not results:
            st.info("No matching sections found.")
        else:
            st.success(f"Found {len(results)} matching sections")
            for r in results:
                with st.expander(f"**{r['act']}** — Section {r['section']}: {r['title']}"):
                    st.write(r.get("text", "")[:500])
                    if r.get("amendments"):
                        st.markdown("🔴 *This section has been amended.*")

with tab3:
    acts_list = [a["name"] for a in list_acts()] if acts else []
    if not acts_list:
        st.warning("No acts in the database.")
    else:
        act_choice = st.selectbox("Select Act", acts_list)
        # Get sections for autocomplete
        act_sections = get_act_sections(act_choice) if act_choice else []
        sec_choices = [f"Section {s['section']} — {s.get('title', '')}" for s in act_sections]
        if sec_choices:
            sec_choice = st.selectbox("Select Section", ["Ask about the Act generally"] + sec_choices)
            section_num = sec_choice.split(" — ")[0].replace("Section ", "") if sec_choice != "Ask about the Act generally" else ""
        else:
            section_num = st.text_input("Section number", placeholder="e.g., 9 or 9A")

        question = st.text_area("Your question", height=80, placeholder="e.g., Does this section apply to foreign nationals?")
        if st.button("Ask AI", type="primary", disabled=not question.strip()):
            with st.spinner("Consulting legal AI..."):
                answer = ask_provision(act_choice, section_num, question)
            st.markdown("### Answer")
            st.write(answer)
