from utils.general import check_patient
from utils.surveys import upsert
from utils.consolidate import recruited, historical

import asyncio
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Update Surveys", layout="wide")
st.title("Update Surveys")
st.divider()

st.subheader("Check Data Quality")

mobile = st.text_input("Mobile number", placeholder="e.g. 13249881445")

check = st.button("Check", type="primary")

if not check:
    pass

elif not mobile:
    st.warning("Please enter a mobile number")

else:
    with st.spinner("Checking database..."):
        res = asyncio.run(check_patient(mobile))

    status = res.get("status")

    if status == "empty":
        st.error(f"❌ {mobile} is invalid / does not exist or the patient has no valid measurements")

    else:
        st.subheader("Patient Measurement Summary")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Measurements", res.get("n_measurements"))
            st.metric("Unique Dates", res.get("n_unique_dates"))

        with col2:
            st.metric("Earliest Measurement", res.get("earliest"))
            st.metric("Latest Measurement", res.get("latest"))

        st.divider()

        if status == "pass":
            st.success(f"✅ {mobile} fulfils study requirements")
            st.balloons()

        elif status == "no_pass":
            st.warning(f"⚠️ {mobile} does not fulfil study requirements")

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
