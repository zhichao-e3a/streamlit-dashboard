from config.configs import ST_CRED

import streamlit as st

from config.configs import REMOTE_MONGO_CONFIG, TEST_MONGO_CONFIG, LOCAL_MONGO_CONFIG
from database_manager.database.mongo import MongoDBConnector

if st.session_state.mode == "TEST": cfg = TEST_MONGO_CONFIG
if st.session_state.mode == "LOCAL": cfg = LOCAL_MONGO_CONFIG
elif st.session_state.mode == "REMOTE": cfg = REMOTE_MONGO_CONFIG

def verify_login(username, password):

    if not username:
        st.warning("Please enter your username")

    elif not password:
        st.warning("Please enter your password")

    elif username == ST_CRED["ST_USER"] and password == ST_CRED["ST_PASS"]:
        st.success("Successfully logged in")
        st.session_state.logged_in = True
        st.rerun()

    else:
        st.warning("Wrong username or password")

async def check_patient(mobile):

    mongo = MongoDBConnector(cfg)

    docs = await mongo.get_all_documents(
        coll_name="RECORDS_PRED",
        query={"mobile": mobile},
        sort=[("measurement_date", 1)]
    )

    # `meaurement_date` in YYYY-MM-DD HH:MM:SS format
    n_unique_dates = len(set([i['measurement_date'][:10] for i in docs]))
    n_measurements = len(docs)

    res = {
        "status"            : "pass",
        "n_measurements"    : n_measurements,
        "n_unique_dates"    : n_unique_dates
    }

    if n_measurements == 0:
        res["status"] = "empty"

    elif n_measurements < 20 or n_unique_dates < 20:
        res["status"] = "no_pass"

    if res["status"] == "pass":
        res["earliest"] = docs[0]['measurement_date']
        res["latest"]   = docs[-1]['measurement_date']

    return res