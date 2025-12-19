from utils.surveys import upsert
from utils.consolidate import recruited, historical

import asyncio
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Update Surveys", layout="wide")
st.title("Update Surveys")
st.divider()

pre_file    = st.file_uploader("Upload Pre-survey CSV", type=["csv"], key="pre_csv")
post_file   = st.file_uploader("Upload Post-survey CSV", type=["csv"], key="post_csv")
hist_file   = st.file_uploader("Upload Historical XLSX", type=["xlsx"], key="hist")

st.divider()

run = st.button("Run pipeline", type="primary", disabled=not (pre_file and post_file and hist_file))

if run:

    with st.status(label="Updating Surveys...", expanded=True) as s:

        st.success("Files uploaded")

        pre_df  = pd.read_csv(pre_file)
        post_df = pd.read_csv(post_file)
        hist_df = pd.read_excel(hist_file)

        messages = asyncio.run(upsert(pre_df, post_df))

        st.subheader("Progress Logs")

        for msg in messages:
            st.write(f"`{msg}`")

        messages = asyncio.run(recruited())

        for msg in messages:
            st.write(f"`{msg}`")

        messages = asyncio.run(historical(hist_df))

        for msg in messages:
            st.write(f"`{msg}`")

        s.update(label="Update Complete", state="complete")
