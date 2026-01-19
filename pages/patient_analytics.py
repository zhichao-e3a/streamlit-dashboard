from cache import get_data

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from datetime import date, datetime
from collections import Counter

st.set_page_config(page_title="Patient Analytics Dashboard", layout="wide")
st.title("Patient Analytics Dashboard")
st.divider()

with st.container():

    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("Start Date", datetime.today(), max_value="today")
    with c2:
        end = st.date_input("End Date", date.today(), max_value="today")

patients = get_data(coll_name="PATIENTS_UNIFIED")


def pct(old, new):
    return ((new - old) / old) * 100


########## Patient Overview ##########
curr_patients = [i for i in patients if i["date_joined"] <= end.strftime("%Y-%m-%d")]
past_patients = [i for i in patients if i["date_joined"] <= start.strftime("%Y-%m-%d")]

rec = [i for i in curr_patients if i["origin"] == "rec"]
past_rec = [i for i in past_patients if i["origin"] == "rec"]

hist = [i for i in curr_patients if i["origin"] == "hist"]
past_hist = [i for i in past_patients if i["origin"] == "hist"]
##################################################

########## Delivery Status ##########
delivered = [i for i in curr_patients if not pd.isna(i["delivery_type"])]
curr_delivered = [i for i in delivered if i["add"] <= end.strftime("%Y-%m-%d")]
past_delivered = [i for i in delivered if i["add"] <= start.strftime("%Y-%m-%d")]

natural = [i for i in curr_delivered if i["delivery_type"] == "natural"]
past_natural = [i for i in past_delivered if i["delivery_type"] == "natural"]

csection = [i for i in curr_delivered if i["delivery_type"] == "c-section"]
past_csection = [i for i in past_delivered if i["delivery_type"] == "c-section"]

ecsection = [i for i in curr_delivered if i["delivery_type"] == "emergency c-section"]
past_ecsection = [
    i for i in past_delivered if i["delivery_type"] == "emergency c-section"
]
##################################################

########## Endpoints Captured ##########
curr_valid = natural + ecsection
past_valid = past_natural + past_ecsection

r_curr_valid = sum([1 for i in curr_valid if i["origin"] == "rec"])
h_curr_valid = sum([1 for i in curr_valid if i["origin"] == "hist"])
r_past_valid = sum([1 for i in past_valid if i["origin"] == "rec"])
h_past_valid = sum([1 for i in past_valid if i["origin"] == "hist"])

onset = [i for i in curr_valid if not pd.isna(i["onset"]) and i["onset"]]
past_onset = [i for i in past_valid if not pd.isna(i["onset"]) and i["onset"]]

r_curr_onset = sum([1 for i in onset if i["origin"] == "rec"])
h_curr_onset = sum([1 for i in onset if i["origin"] == "hist"])
r_past_onset = sum([1 for i in past_onset if i["origin"] == "rec"])
h_past_onset = sum([1 for i in past_onset if i["origin"] == "hist"])

add = [i for i in curr_valid if not pd.isna(i["add"]) and i["add"]]
past_add = [i for i in past_valid if not pd.isna(i["add"]) and i["add"]]

r_curr_add = sum([1 for i in add if i["origin"] == "rec"])
h_curr_add = sum([1 for i in add if i["origin"] == "hist"])
r_past_add = sum([1 for i in past_add if i["origin"] == "rec"])
h_past_add = sum([1 for i in past_add if i["origin"] == "hist"])

missing_targets = pd.DataFrame(columns=["Mobile", "Origin", "Onset", "Actual Delivery"])
for i in curr_valid:

    f_add, f_onset = i["add"], i["onset"]

    if pd.isna(f_add) or not f_add:
        f_add = "MISSING"

    if pd.isna(f_onset) or not f_onset:
        f_onset = "MISSING"

    if f_add == "MISSING" or f_onset == "MISSING":
        missing_targets.loc[len(missing_targets)] = {
            "Mobile": i["mobile"],
            "Origin": i["origin"],
            "Onset": f_onset,
            "Actual Delivery": f_add,
        }
##################################################

########## Delivery Forecast ##########
not_delivered = [i for i in patients if pd.isna(i["delivery_type"])]

forecast_table = [
    {
        "Mobile": i["mobile"],
        "Origin": i["origin"],
        "Expected Delivery": i["edd"],
        "Expected Days to Delivery": (
            datetime.strptime(i["edd"], "%Y-%m-%d").date() - date.today()
        ).days,
    }
    for i in not_delivered
    if i["edd"]
]

forecast_table.sort(key=lambda x: x["Expected Delivery"])

edd = [i for i in forecast_table if i["Expected Days to Delivery"] >= 0]

weeks = [i["Expected Days to Delivery"] // 7 + 1 for i in edd]
weeks_dic = dict(Counter(weeks))
sorted_weeks_dic = dict(sorted(weeks_dic.items()))

past_edd = [i for i in forecast_table if i["Expected Days to Delivery"] < 0]

missing_edd = [
    {"Mobile": i["mobile"], "Origin": i["origin"]}
    for i in not_delivered
    if not i["edd"]
]
##################################################

########## Report by Gestational Age ##########
ga_entry = [int(i["ga_entry"] / 7) for i in patients]
ga_entry_dic = dict(Counter(ga_entry))
sorted_ga_entry_dic = dict(sorted(ga_entry_dic.items()))

ga_exit_add = [
    int(i["ga_exit_add"] / 7) for i in patients if not pd.isna(i["ga_exit_add"])
]
ga_exit_add_dic = dict(Counter(ga_exit_add))
sorted_ga_exit_add_dic = dict(sorted(ga_exit_add_dic.items()))

ga_df = pd.DataFrame(
    {
        "Mobile": [i["mobile"] for i in patients],
        "Gestational Age at Entry": ga_entry,
        "Gestational Age at Last Measurement": [
            int(i["ga_exit_last"] / 7) if pd.notna(i["ga_exit_last"]) else 0
            for i in patients
        ],
        "Gestational Age at Delivery": [
            int(i["ga_exit_add"] / 7) if pd.notna(i["ga_exit_add"]) else 0
            for i in patients
        ],
    }
)

ga_df = ga_df.sort_values(
    ["Gestational Age at Entry", "Gestational Age at Delivery"], ascending=[True, False]
)

error_ga = [
    i for i in ga_df.to_dict("records") if (i["Gestational Age at Delivery"] > 45)
]
error_ga.sort(key=lambda x: x["Gestational Age at Delivery"], reverse=False)
##################################################

with st.container():

    st.subheader(f"`Data from {start} to {end}`")

    st.download_button(
        "Download CSV Report",
        data=pd.DataFrame(patients).to_csv(),
        file_name="patients_unified.csv",
    )

with st.container():

    st.subheader("Patient Overview")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(
            "Total Patients",
            len(curr_patients),
            border=True,
            delta=len(curr_patients) - len(past_patients),
        )
    with c2:
        st.metric("Recruited", len(rec), border=True, delta=len(rec) - len(past_rec))
    with c3:
        st.metric(
            "Historical", len(hist), border=True, delta=len(hist) - len(past_hist)
        )

with st.container():

    st.subheader("Delivery Status")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "Delivered",
            len(curr_delivered),
            border=True,
            delta=len(curr_delivered) - len(past_delivered),
        )
    with c2:
        st.metric(
            "Natural", len(natural), border=True, delta=len(natural) - len(past_natural)
        )
    with c3:
        st.metric(
            "Emergency C-section",
            len(ecsection),
            border=True,
            delta=len(ecsection) - len(past_ecsection),
        )
    with c4:
        st.metric(
            "C-section",
            len(csection),
            border=True,
            delta=len(csection) - len(past_csection),
        )

with st.container():

    st.subheader("Endpoints Captured (for Natural, Emergency C-section)")

    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.metric(
                "Total Valid",
                len(curr_valid),
                border=False,
                delta=len(curr_valid) - len(past_valid),
            )
            r, h = st.columns(2)
            with r:
                st.metric(
                    "Recruited",
                    r_curr_valid,
                    border=False,
                    delta=r_curr_valid - r_past_valid,
                )
            with h:
                st.metric(
                    "Historical",
                    h_curr_valid,
                    border=False,
                    delta=h_curr_valid - h_past_valid,
                )
    with c2:
        with st.container(border=True):
            st.metric(
                "With Onset Datetime",
                len(onset),
                border=False,
                delta=len(onset) - len(past_onset),
            )
            r, h = st.columns(2)
            with r:
                st.metric(
                    "Recruited",
                    r_curr_onset,
                    border=False,
                    delta=r_curr_onset - r_past_onset,
                )
            with h:
                st.metric(
                    "Historical",
                    h_curr_onset,
                    border=False,
                    delta=h_curr_onset - h_past_onset,
                )
    with c3:
        with st.container(border=True):
            st.metric(
                "With Delivery Datetime",
                len(add),
                border=False,
                delta=len(add) - len(past_add),
            )
            r, h = st.columns(2)
            with r:
                st.metric(
                    "Recruited", r_curr_add, border=False, delta=r_curr_add - r_past_add
                )
            with h:
                st.metric(
                    "Historical",
                    h_curr_add,
                    border=False,
                    delta=h_curr_add - h_past_add,
                )

    st.write("Patients with either missing onset or actual delivery date")
    st.dataframe(missing_targets)

st.divider()

with st.container():

    st.subheader(f"Delivery Forecast ({date.today()})")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Not delivered", len(not_delivered), border=True)
    with c2:
        st.metric("Expected to Deliver", len(edd), border=True)
    with c3:
        st.metric("Past Expected Delivery", len(past_edd), border=True)
    with c4:
        st.metric("Missing Expected Delivery", len(missing_edd), border=True)

    st.write("Patients Expected to Deliver")
    st.dataframe(edd)

    st.write("Patients Expected to Deliver by Weeks")
    st.bar_chart(sorted_weeks_dic, x_label="Weeks to Delivery", y_label="Patient Count")

    st.write("Patients Past Expected Delivery")
    st.dataframe(past_edd)

    st.write("Patients with Missing Expected Delivery")
    st.dataframe(missing_edd)

st.divider()

with st.container():

    st.subheader(f"Report by Gestational Age ({date.today()})")

    st.write(f"Gestational Age Weeks at Entry ({len(ga_entry)} patients)")
    st.bar_chart(
        sorted_ga_entry_dic,
        x_label="Gestational Age Weeks (Entry)",
        y_label="Patient Count",
    )

    st.write(f"Gestational Age Weeks at Exit ({len(ga_exit_add)} patients)")
    st.bar_chart(
        sorted_ga_exit_add_dic,
        x_label="Gestational Age Weeks (Exit)",
        y_label="Patient Count",
    )

    st.write("Gestational Age Weeks Analysis per Patient")
    n = len(ga_df)

    window = st.number_input("Rows per page", min_value=8, max_value=n, value=8, step=1)

    max_start = max(0, n - window)

    if "start_idx" not in st.session_state:
        st.session_state.start_idx = 0

    prev_col, next_col = st.columns(2)
    with prev_col:
        if st.button("Previous", width="stretch"):
            st.session_state.start_idx = max(0, st.session_state.start_idx - window)
    with next_col:
        if st.button("Next", width="stretch"):
            st.session_state.start_idx = min(
                max_start, st.session_state.start_idx + window
            )

    start = st.session_state.start_idx
    end = min(start + window, n)

    subset = ga_df.iloc[start:end].copy()

    len_add = (
        (subset["Gestational Age at Delivery"] - subset["Gestational Age at Entry"])
        .clip(lower=0)
        .fillna(0)
    )
    len_last = (
        (
            subset["Gestational Age at Last Measurement"]
            - subset["Gestational Age at Entry"]
        )
        .clip(lower=0)
        .fillna(0)
    )

    fig = go.Figure()

    fig.add_bar(
        y=subset["Mobile"],
        x=len_last,
        base=subset["Gestational Age at Entry"],
        orientation="h",
        name="Last Measurement",
        text=(
            subset["Gestational Age at Entry"].astype(str)
            + "→"
            + subset["Gestational Age at Last Measurement"].astype(str)
        ),
        textposition="outside",
    )

    fig.add_bar(
        y=subset["Mobile"],
        x=len_add,
        base=subset["Gestational Age at Entry"],
        orientation="h",
        name="Actual Delivery",
        text=(
            subset["Gestational Age at Entry"].astype(str)
            + "→"
            + subset["Gestational Age at Delivery"].astype(str)
        ),
        textposition="outside",
    )

    fig.update_layout(
        barmode="group",
        title=f"Total {n} patients: Patients {start+1} to {end}",
        bargap=0.35,
        height=600,
    )

    fig.update_xaxes(range=[25, 45], title="Gestational Age (weeks)")

    fig.update_yaxes(type="category", title="Patient")

    st.plotly_chart(fig, width="stretch")

    st.write("Patients with Erroneous Gestational Age")
    st.dataframe(error_ga)

st.divider()

with st.container():

    all_mobile = [i["mobile"] for i in patients]
    p_mobile = st.selectbox("Select Patient", all_mobile)
    p_data = [i for i in patients if i["mobile"] == p_mobile]

    st.subheader(f"Patient Data for {p_mobile}")

    st.table(pd.DataFrame(p_data).melt(var_name="Field", value_name="Value"))
