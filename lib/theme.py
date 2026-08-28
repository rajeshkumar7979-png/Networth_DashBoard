import streamlit as st

def inject_css():
    st.markdown("""
    <style>
    .stApp { background: #0a0e17; color: #e5e9f0; }
    </style>
    """, unsafe_allow_html=True)
