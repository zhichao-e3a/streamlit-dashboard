from cache import get_data

import pandas as pd
import streamlit as st

st.set_page_config(page_title="EDA Dashboard", layout="wide")
st.title("Data Analytics Dashboard")
st.divider()

DATASET_OPTIONS = {
    "Recruited + Contacted Historical   (Onset Target, no C-section)": "dataset_onset",
    "Recruited + Contacted Historical   (ADD Target, no C-section)": "dataset_add",
    "All Historical Only                (ADD Target, all delivery types)": "dataset_hist",
    "Recruited + All Historical         (ADD Target, all delivery types)": "dataset_all",
}

with st.container():

    st.subheader("Dataset Selection")

    selected_label = st.selectbox(
        "Choose dataset to view",
        options=list(DATASET_OPTIONS.keys()),
        index=0,
    )

    coll_name = DATASET_OPTIONS[selected_label]

st.divider()

data = get_data(
    coll_name=coll_name,
    projection={
        "_id": 0,
        "uc_raw": 0,
        "fhr_raw": 0,
        "fmov_raw": 0,
        "uc_padded": 0,
        "fhr_padded": 0,
        "fmov_padded": 0,
        "uc_windows": 0,
        "fhr_windows": 0,
        "ctime": 0,
        "utime": 0,
        "doc_hash": 0,
    },
    limit=None,
)

df = pd.DataFrame(data)

for col in ["add", "onset", "measurement_date"]:
    df[col] = pd.to_datetime(df[col], errors="coerce")

df["ga_days"] = df["static"].apply(lambda x: x[-1])
df["ga_weeks"] = (df["ga_days"] / 7).round().astype("Float64")

with st.container():

    week_options = df["ga_weeks"].dropna().astype(int).sort_values().unique().tolist()

    selected_weeks = st.multiselect(
        "Gestational Age Weeks Filter",
        week_options,
        default=week_options,
    )

    if selected_weeks:
        df_filtered = df[df["ga_weeks"].astype("Int64").isin(selected_weeks)]
    else:
        df_filtered = df.copy()

with st.container():

    st.subheader("Patient Overview")

    patients = (
        df_filtered.groupby("mobile")
        .agg(
            preterm=("preterm", "max"),
            measurements=("target", "count"),
            min_target=("target", "min"),
            max_target=("target", "max"),
        )
        .sort_values("measurements", ascending=True)
        .reset_index()
    )

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Total Patients", value=len(patients), border=True)
        st.dataframe(patients, width="stretch")

    with c2:
        preterm = patients[patients["preterm"] == 1].copy()
        st.metric("Preterm Patients", value=len(preterm), border=True)
        if preterm.empty:
            st.info("No preterm patients")
        else:
            st.dataframe(preterm.reset_index(drop=True), width="stretch")

    c1, c2 = st.columns(2)

    with c1:
        low_count = (
            patients[patients["measurements"] < 20]
            .copy()
            .drop(["preterm", "min_target", "max_target"], axis=1)
        )
        st.metric(f"Patients < 20 measurements", value=len(low_count), border=True)
        if low_count.empty:
            st.info("No patients with fewer than 20 measurements")
        else:
            st.dataframe(low_count.reset_index(drop=True), width="stretch")

    with c2:
        long_min_target = (
            patients[patients["min_target"] > 7]
            .copy()
            .sort_values("min_target", ascending=False)
            .drop(["preterm", "max_target"], axis=1)
        )
        st.metric(
            f"Patients min_target > 7 days", value=len(long_min_target), border=True
        )
        if long_min_target.empty:
            st.info("No patients with min_target > 7 days.")
        else:
            st.dataframe(long_min_target.reset_index(drop=True), width="stretch")

st.divider()

with st.container():

    st.subheader("Single Patient View")

    patient_mobile = None
    mobile_values = df["mobile"].dropna().astype(str).sort_values().unique().tolist()

    if mobile_values:
        patient_mobile = st.selectbox(
            "Select Patient",
            options=mobile_values,
            index=0,
        )
    else:
        st.info("No 'mobile' field found for patient-level view.")

    patient_df = df[df["mobile"].astype(str) == str(patient_mobile)].copy()

    if patient_df.empty:
        st.write(f"No records found for patient {patient_mobile}.")
    else:
        patient_df = patient_df.sort_values("measurement_date")
        time_col = "measurement_date"

        st.write(f"**Patient `{patient_mobile}`**")

        cols_to_show = []
        for col in ["measurement_date", "ga_weeks", "target", "add", "onset"]:
            cols_to_show.append(col)

        st.write("Measurements (sorted by date):")
        st.dataframe(
            patient_df[cols_to_show],
            width="stretch",
        )

        plot_df = patient_df.dropna(subset=[time_col, "target"]).set_index(time_col)
        if not plot_df.empty:
            st.write("Target trajectory over time:")
            st.line_chart(plot_df["target"])

st.divider()

with st.container():

    st.subheader("Target by Gestational Age Week")

    ga_df = df_filtered.dropna(subset=["ga_weeks", "target"])

    if ga_df.empty:
        st.write("No records.")

    else:
        agg = (
            ga_df.assign(ga_weeks_int=ga_df["ga_weeks"].astype(int))
            .groupby("ga_weeks_int")["target"]
            .agg(["count", "min", "mean", "max"])
            .reset_index()
            .rename(
                columns={
                    "ga_weeks_int": "GA Week",
                    "count": "Count",
                    "min": "Min Target",
                    "mean": "Avg Target",
                    "max": "Max Target",
                }
            )
        )

        c1, c2 = st.columns([2, 3])

        with c1:
            st.write("Summary Table")
            st.dataframe(
                agg.style.format(
                    {
                        "Min Target": "{:.2f}",
                        "Avg Target": "{:.2f}",
                        "Max Target": "{:.2f}",
                    }
                ),
                width="stretch",
            )

        with c2:
            st.write("Average Target by GA Week")
            chart_data = agg.set_index("GA Week")[["Avg Target"]]
            st.bar_chart(chart_data)
