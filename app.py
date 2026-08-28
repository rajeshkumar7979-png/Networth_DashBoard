import streamlit as st
from lib.theme import inject_css

st.set_page_config(
    page_title="Family Net Worth",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

pg = st.navigation({
    "Workspace": [
        st.Page("pages/1_Command_Center.py", title="Command Center", icon="📊", default=True),
        st.Page("pages/2_Deep_Health.py", title="Deep Health", icon="🩺"),
        st.Page("pages/3_Asset_Detail.py", title="Asset Detail", icon="📁"),
    ]
})
pg.run()
