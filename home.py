"""
MLB Pitch Analytics — Streamlit entry point.

Run:
    streamlit run home.py

Each report lives under reports/<name>/page.py and is registered below.
To add a new report: drop a folder under reports/, add an entry to REPORTS.
"""

import streamlit as st

st.set_page_config(page_title="MLB Pitch Analytics", layout="wide")


REPORTS = [
    {
        "path": "reports/first_pitch_offspeed/page.py",
        "title": "First-pitch offspeed: CSW% & whiff%",
        "icon": ":material/sports_baseball:",
        "summary": (
            "Do hard throwers (96+ mph fastball) get more CSW% / whiffs when "
            "leading an at-bat with an offspeed pitch than soft throwers? "
            "Splits by velo and 4-seam vs. offspeed vertical separation. Toggle "
            "CSW% (called strikes + whiffs / pitches) or whiff% as the headline metric."
        ),
    },
]


def home():
    st.title("MLB Pitch Analytics")
    st.caption("Pick a report from the sidebar, or jump in below.")
    st.divider()
    for r in REPORTS:
        with st.container(border=True):
            st.subheader(r["title"])
            st.write(r["summary"])
            st.page_link(r["path"], label=f"Open: {r['title']}", icon=r["icon"])


nav = st.navigation(
    {
        "": [st.Page(home, title="Home", icon=":material/home:", default=True)],
        "Reports": [
            st.Page(r["path"], title=r["title"], icon=r["icon"])
            for r in REPORTS
        ],
    }
)
nav.run()
