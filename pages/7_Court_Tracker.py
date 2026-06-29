import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime, date

st.set_page_config(page_title="Court Tracker", page_icon="🗓️", layout="wide")
st.title("🗓️ Court Date & Case Status Tracker")
st.caption("Track all your cases, hearing dates, and court status — with eCourts integration.")

from core.court_tracker import (
    get_all_cases, add_case, update_case, add_hearing,
    delete_case, fetch_ecourts_status, get_upcoming_dates,
)

tab1, tab2, tab3 = st.tabs(["📋 My Cases", "➕ Add Case", "🔔 Upcoming Dates"])

with tab1:
    cases = get_all_cases()
    if not cases:
        st.info("No cases added yet. Use the 'Add Case' tab to add your first case.")
    else:
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Cases", len(cases))
        upcoming = get_upcoming_dates(7)
        col2.metric("Hearings This Week", len(upcoming))
        col3.metric("Active Cases", sum(1 for c in cases if c.get("status") != "Disposed"))

        st.markdown("---")
        for case in cases:
            with st.expander(f"📁 {case['case_name']} — {case.get('court', '')} | Next: {case.get('next_date', 'TBD')}"):
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Case No:** {case.get('case_number', '-')}")
                c1.write(f"**CNR:** {case.get('cnr_number', '-')}")
                c2.write(f"**Parties:** {case.get('parties', '-')}")
                c2.write(f"**Status:** {case.get('status', 'Pending')}")
                c3.write(f"**Next Date:** {case.get('next_date', 'TBD')}")
                c3.write(f"**Notes:** {case.get('notes', '-')}")

                # Hearing history
                hearings = case.get("hearings", [])
                if hearings:
                    st.markdown("**Hearing History:**")
                    hdf = pd.DataFrame(hearings)[["date", "outcome"]]
                    st.dataframe(hdf, use_container_width=True, hide_index=True)

                # Actions
                a1, a2, a3 = st.columns(3)
                with a1:
                    new_next = st.date_input("Update next date", key=f"nd_{case['id']}")
                    outcome_txt = st.text_input("Hearing outcome", key=f"out_{case['id']}", placeholder="e.g., Arguments heard, adjourned")
                    if st.button("Add Hearing", key=f"ah_{case['id']}"):
                        add_hearing(case["id"], str(new_next), outcome_txt, str(new_next))
                        st.rerun()
                with a2:
                    new_status = st.selectbox("Update status", ["Pending", "Active", "Reserved", "Disposed", "Stayed"], key=f"st_{case['id']}")
                    if st.button("Update Status", key=f"us_{case['id']}"):
                        update_case(case["id"], status=new_status)
                        st.rerun()
                with a3:
                    if case.get("cnr_number"):
                        if st.button("🔄 Fetch eCourts Status", key=f"ec_{case['id']}"):
                            with st.spinner("Fetching from eCourts..."):
                                ecourts = fetch_ecourts_status(case["cnr_number"])
                            if "error" in ecourts:
                                st.warning(ecourts["error"])
                            else:
                                st.json(ecourts)
                    if st.button("🗑️ Delete", key=f"del_{case['id']}"):
                        delete_case(case["id"])
                        st.rerun()

with tab2:
    st.subheader("Add New Case")
    with st.form("add_case_form"):
        case_name = st.text_input("Case Name *", placeholder="ABC vs XYZ")
        col1, col2 = st.columns(2)
        with col1:
            court_name = st.text_input("Court / Forum *", placeholder="High Court of Delhi")
            case_number = st.text_input("Case Number", placeholder="CS(OS) 123/2024")
        with col2:
            cnr = st.text_input("CNR Number", placeholder="DLHC01234562024")
            parties = st.text_input("Parties", placeholder="Petitioner, Respondent")
        next_d = st.date_input("Next Hearing Date")
        notes = st.text_area("Notes", height=80)

        # eCourts fetch option
        st.markdown("**Or fetch status from eCourts:**")
        cnr_fetch = st.text_input("Enter CNR to look up", key="cnr_lookup")
        if st.form_submit_button("Fetch from eCourts"):
            if cnr_fetch:
                with st.spinner("Fetching..."):
                    result = fetch_ecourts_status(cnr_fetch)
                if "error" in result:
                    st.warning(result["error"])
                else:
                    st.json(result)
                    st.info("Review the data above and fill the form accordingly.")

        submitted = st.form_submit_button("Add Case", type="primary")
        if submitted:
            if not case_name or not court_name:
                st.error("Case Name and Court are required.")
            else:
                add_case(case_name, court_name, case_number, cnr, parties, str(next_d), notes)
                st.success(f"Case '{case_name}' added!")
                st.rerun()

with tab3:
    st.subheader("Upcoming Hearings")
    days = st.slider("Show hearings within the next N days:", 7, 90, 30)
    upcoming = get_upcoming_dates(days)
    if not upcoming:
        st.info("No upcoming hearings in this period.")
    else:
        for u in upcoming:
            days_away = u["days_away"]
            label = "TODAY" if days_away == 0 else f"in {days_away} day(s)"
            color = "red" if days_away <= 3 else "orange" if days_away <= 7 else "green"
            st.markdown(
                f":{color}[**{u['next_date']}** ({label})] — {u['case_name']} @ {u.get('court', '-')}"
            )
