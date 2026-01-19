from utils.general import *

import streamlit as st

st.set_page_config(
    page_title="E3A AI Monitoring Dashboard", page_icon=":hospital:", layout="wide"
)
st.title("E3A Healthcare (AI Monitoring Dashboard)")
st.divider()

with st.container():

    left, mid, right = st.columns(3)

    with mid:

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login", width="stretch"):
            verify_login(username, password)
