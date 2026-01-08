from config.configs import REMOTE_MONGO_CONFIG, TEST_MONGO_CONFIG, LOCAL_MONGO_CONFIG
from pymongo import MongoClient

import streamlit as st

if st.session_state.mode == "TEST": cfg = TEST_MONGO_CONFIG
if st.session_state.mode == "LOCAL": cfg = LOCAL_MONGO_CONFIG
elif st.session_state.mode == "REMOTE": cfg = REMOTE_MONGO_CONFIG

@st.cache_data(show_spinner=True, ttl=60)
def get_data(coll_name: str, projection: dict=None, limit: int=None):

    uri     = cfg['DB_HOST']
    db_name = cfg["DB_NAME"]
    client  = MongoClient(uri)
    coll    = client[db_name][coll_name]

    docs = coll.find({}, projection or {"_id": 0})

    if limit:
        docs = docs.limit(limit)

    docs_list = list(docs)

    client.close()

    return docs_list
