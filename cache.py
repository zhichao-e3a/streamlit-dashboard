from config.configs import REMOTE_MONGO_CONFIG, TEST_MONGO_CONFIG, LOCAL_MONGO_CONFIG
from pymongo import MongoClient

import logging
import os
import sys
import tempfile
from datetime import datetime

import streamlit as st


def get_cfg():
    mode = st.session_state.get("mode")
    if mode == "TEST":
        return TEST_MONGO_CONFIG
    elif mode == "LOCAL":
        return LOCAL_MONGO_CONFIG
    elif mode == "REMOTE":
        return REMOTE_MONGO_CONFIG
    raise ValueError("st.session_state.mode must be one of: TEST, LOCAL, REMOTE")


@st.cache_resource(show_spinner=False)
def setup_logging(level: int = logging.INFO, log_dir: str = None) -> logging.Logger:

    logger = logging.getLogger()

    if not logger.handlers:

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")

        base_dir = log_dir or os.getenv("LOG_DIR", "logs")
        try:
            os.makedirs(base_dir, exist_ok=True)
            log_path = os.path.join(base_dir, f"{ts}.log")
            file_handler = logging.FileHandler(log_path, encoding="utf-8")

        except OSError:
            temp_dir = os.path.join(tempfile.gettempdir(), "streamlit-logs")
            os.makedirs(temp_dir, exist_ok=True)
            log_path = os.path.join(temp_dir, f"{ts}.log")
            file_handler = logging.FileHandler(log_path, encoding="utf-8")

        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s"
        )

        file_handler.setFormatter(formatter)
        handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(handler)

    logger.setLevel(level)

    return logger


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


@st.cache_data(show_spinner=True, ttl=60)
def get_data(coll_name: str, projection: dict = None, limit: int = None):

    cfg = get_cfg()
    uri = cfg["DB_HOST"]
    db_name = cfg["DB_NAME"]
    client = MongoClient(uri)
    coll = client[db_name][coll_name]

    docs = coll.find({}, projection or {"_id": 0})

    if limit:
        docs = docs.limit(limit)

    docs_list = list(docs)

    client.close()

    return docs_list
