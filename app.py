import streamlit as st

st.set_page_config(
    page_title="Family Net Worth",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Family Net Worth")
st.markdown(
    """
**Portfolio Command Center** for the family book.

Use the **sidebar** (pages list):

- **Command Center** — live net worth, allocation, holdings  
- **Deep Health** — decision desk  
- **Asset Detail** — deep health for one holding (also via links from Command Center)
"""
)

st.page_link("pages/1_Command_Center.py", label="Open Command Center", icon="📊")
st.page_link("pages/2_Deep_Health.py", label="Open Deep Health", icon="🩺")
st.page_link("pages/3_Asset_Detail.py", label="Open Asset Detail", icon="🔎")

st.caption(
    "After Streamlit Cloud redeploys, open **Command Center** from the sidebar. "
    "Root app.py is only the menu."
)
