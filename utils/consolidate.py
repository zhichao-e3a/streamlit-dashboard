from cache import get_cfg, get_logger
from config.configs import (
    REMOTE_MONGO_CONFIG,
    TEST_MONGO_CONFIG,
    LOCAL_MONGO_CONFIG,
    SQL_CONFIG,
)
from database_manager.database.mongo import MongoDBConnector
from database_manager.database.mysql import SQLDBConnector
from database_manager.database.queries import HISTORICAL_METADATA_QUERY

import json
import pandas as pd
import streamlit as st
from typing import Any, Optional

# import numpy as np
# from datetime import datetime

logger = get_logger(__name__)


def delivery_type_map(s: Any) -> Any:
    s = "" if s is None else str(s)
    if "顺产" in s:
        return "natural"
    if "剖腹产（剖宫产）" in s:
        return "c-section"
    if "紧急剖腹产" in s:
        return "emergency c-section"
    return None


def bmi_choose_weight_kg(height_cm: Any, weight_val: Any) -> Optional[float]:
    """
    Resolve 斤 vs kg:
      - If weight > 110 → treat as 斤 (kg = x * 0.5)
      - Else compute BMI for both kg and 斤 and pick the one within [15, 45].
        If both plausible or both implausible, default to kg when <= 110.
    """

    def _try_float(x: Any) -> Optional[float]:
        try:
            return float(str(x).strip())
        except Exception as e:
            logger.debug("Failed to parse float from %r: %s", x, e)
            return None

    h_cm = pd.to_numeric(height_cm, errors="coerce")
    w = _try_float(weight_val)
    if pd.isna(h_cm) or h_cm <= 0 or w is None:
        return None

    h_m = h_cm / 100.0
    kg_if_kg = w
    kg_if_jin = w * 0.5

    def _bmi(kg: Optional[float]) -> Optional[float]:
        return (kg / (h_m**2)) if (kg and h_m > 0) else None

    b1 = _bmi(kg_if_kg)
    b2 = _bmi(kg_if_jin)

    def plausible(b: Optional[float]) -> bool:
        return (b is not None) and (15.0 <= b <= 45.0)

    if w > 110:
        return round(b2, 1) if b2 is not None else None
    if plausible(b1) and not plausible(b2):
        return round(b1, 1)
    if plausible(b2) and not plausible(b1):
        return round(b2, 1)
    return round(b1, 1) if b1 is not None else None


def flag_contains_1_0(text: Any, needle: str) -> int:
    return 1 if (text is not None and needle in str(text)) else 0


def compute_onset(row: pd.Series) -> str:
    """Onset = parsed water_break_datetime, else ''."""

    def parse_water_break_datetime(wb: Any) -> Optional[pd.Timestamp]:
        """Expect 'YYYY-MM-DD HH:MM' or '' from Mongo; return Timestamp or None."""
        s = "" if wb is None else str(wb).strip()
        if not s:
            return None
        t = pd.to_datetime(s, format="%Y-%m-%d %H:%M", errors="coerce")
        return t if pd.notna(t) else None

    ts = parse_water_break_datetime(row.get("water_break_datetime"))
    return ts.strftime("%Y-%m-%d %H:%M") if ts is not None else None


def extract_gest_age(conclusion: str, basic_info: str) -> Optional[int]:

    gest_age = None
    basic_info_json = json.loads(basic_info)

    # Check if gest_age can be obtained from 'basic_info' field
    if basic_info_json["setPregTime"]:

        gest_string = basic_info_json["pregTime"]

        digits = [int(c) for c in gest_string if c.isdigit()]

        if len(digits) == 3:
            gest_age = digits[0] * 10 * 7 + digits[1] * 7 + digits[2]
        elif len(digits) == 2:
            gest_age = digits[0] * 10 * 7 + digits[1] * 7

    # If 'conclusion' field available and gest_age still not found
    if conclusion and not gest_age:

        gest_string = conclusion.split("。")[0]

        digits = [int(c) for c in gest_string if c.isdigit()]

        if len(digits) == 3:
            gest_age = digits[0] * 10 * 7 + digits[1] * 7 + digits[2]
        elif len(digits) == 2:
            gest_age = digits[0] * 10 * 7 + digits[1] * 7

    return gest_age


async def recruited():

    logger.info(f"UPDATING METADATA_REC, METADATA_PRED: {st.session_state.mode}")

    cfg = get_cfg()
    mongo = MongoDBConnector(cfg)
    messages = []

    # * Query all records from POST_SURVEY
    all_post_docs = await mongo.get_all_documents(
        "POST_SURVEY",
        projection={
            "_id": 0,
            "mobile": 1,
            "delivery_type": 1,
            "add": 1,
            "delivery_time": 1,
            "water_break_datetime": 1,
        },
    )

    msg = f"{len(all_post_docs)} RECORDS FETCHED FROM POST_SURVEY"
    logger.info(msg)
    messages.append(msg)

    # * Obtain unique records from POST_SURVEY
    all_given_birth = set([i["mobile"] for i in all_post_docs])
    msg = f"{len(all_given_birth)} UNIQUE RECORDS FROM POST_SURVEY"
    logger.info(msg)
    messages.append(msg)

    # * Query all records from PRE_SURVEY
    all_pre_docs = await mongo.get_all_documents(
        "PRE_SURVEY",
        projection={
            "_id": 0,
            "name": 1,
            "mobile": 1,
            "age": 1,
            "curr_height": 1,
            "pre_weight": 1,
            "edd": 1,
            "had_pregnancy": 1,
            "had_preterm": 1,
            "had_surgery": 1,
            "diagnosed_conditions": 1,
        },
    )

    msg = f"{len(all_pre_docs)} RECORDS FETCHED FROM PRE_SURVEY"
    logger.info(msg)
    messages.append(msg)

    # * Obtain unique records from PRE_SURVEY
    all_recruited = set([i["mobile"] for i in all_pre_docs])
    msg = f"{len(all_recruited)} UNIQUE RECORDS FROM PRE_SURVEY"
    logger.info(msg)
    messages.append(msg)

    # * Query all records from METADATA_REC
    metadata_rec = await mongo.get_all_documents(coll_name="METADATA_REC")
    msg = f"{len(metadata_rec)} RECORDS FETCHED FROM METADATA_REC"
    logger.info(msg)
    messages.append(msg)

    # * Obtain existing patients who have given birth (stored in METADATA_REC)
    curr_given_birth = set([i["mobile"] for i in metadata_rec])
    msg = f"{len(curr_given_birth)} UNIQUE RECORDS FROM METADATA_REC"
    logger.info(msg)
    messages.append(msg)

    metadata_pred = await mongo.get_all_documents(coll_name="METADATA_PRED")
    msg = f"{len(metadata_pred)} RECORDS FETCHED FROM METADATA_PRED"
    logger.info(msg)
    messages.append(msg)

    # * Obtain existing patients who have yet to give birth (stored in METADATA_PRED)
    curr_not_given_birth = set([i["mobile"] for i in metadata_pred])
    msg = f"{len(curr_not_given_birth)} UNIQUE RECORDS FROM METADATA_PRED"
    logger.info(msg)
    messages.append(msg)

    # * Obtain new patients who have not given birth yet.
    # * Patients who have not given birth only fill in pre but not post.
    # * This is calculated by taking (PRE_SURVEY - POST_SURVEY) records.
    all_not_given_birth = all_recruited - all_given_birth
    msg = f"(PRE_SURVEY - POST_SURVEY) = {len(all_not_given_birth)} PATIENTS YET TO GIVE BIRTH"
    logger.info(msg)
    messages.append(msg)

    # * Obtain new patients who have given birth.
    new_given_birth = all_given_birth - curr_given_birth
    msg = f"{len(new_given_birth)} NEW PATIENTS FINISHED STUDY"
    logger.info(msg)
    messages.append(msg)
    for i in new_given_birth:
        msg = f"{i} FINISHED STUDY"
        logger.info(msg)
        messages.append(msg)

    # * Obtain new patients who have yet to give birth.
    new_not_given_birth = all_not_given_birth - curr_not_given_birth
    msg = f"{len(new_not_given_birth)} NEW PATIENTS ADDED TO STUDY"
    logger.info(msg)
    messages.append(msg)
    for i in new_not_given_birth:
        msg = f"{i} ADDED TO STUDY"
        logger.info(msg)
        messages.append(msg)

    # * Left join pre-survey with post-survey records
    merged = pd.DataFrame(all_pre_docs).merge(
        pd.DataFrame(all_post_docs), on="mobile", how="left", suffixes=("_pre", "_post")
    )

    merged["origin"] = "REC"
    merged["age"] = pd.to_numeric(merged["age"], errors="coerce").astype("Int64")
    merged["had_pregnancy"] = (merged["had_pregnancy"] == "Yes").astype("Int64")
    merged["had_preterm"] = (merged["had_preterm"] == "Yes").astype("Int64")
    merged["had_surgery"] = (merged["had_surgery"] == "Yes").astype("Int64")

    merged["bmi"] = merged.apply(
        lambda r: bmi_choose_weight_kg(r["curr_height"], r["pre_weight"]), axis=1
    )
    merged["gdm"] = merged.apply(
        lambda r: flag_contains_1_0(r["diagnosed_conditions"], "妊娠糖尿病"), axis=1
    )
    merged["pih"] = merged.apply(
        lambda r: flag_contains_1_0(r["diagnosed_conditions"], "妊娠高血压"), axis=1
    )
    merged["delivery_type"] = merged.apply(
        lambda r: delivery_type_map(r["delivery_type"]), axis=1
    )
    merged["add"] = merged.apply(
        lambda r: f"{r['add']} {r['delivery_time']}" if pd.notna(r["add"]) else None,
        axis=1,
    )
    merged["onset"] = merged.apply(lambda r: compute_onset(r), axis=1)

    merged["processed"] = False

    merged.drop(
        columns=[
            "curr_height",
            "pre_weight",
            "water_break_datetime",
            "diagnosed_conditions",
            "delivery_time",
        ],
        inplace=True,
    )

    new_given_birth_df = merged[merged["mobile"].isin(new_given_birth)]
    new_not_given_birth_df = merged[merged["mobile"].isin(new_not_given_birth)]

    update_not_given_birth = new_not_given_birth_df.to_dict(orient="records")
    update_given_birth = new_given_birth_df.to_dict(orient="records")

    await mongo.upsert_documents_hashed(
        coll_name="METADATA_REC", records=update_given_birth, id_fields=["mobile"]
    )

    msg = f"{len(update_given_birth)} RECORDS ADDED TO METADATA_REC"
    logger.info(msg)
    messages.append(msg)

    for m in new_given_birth:
        await mongo.delete_document(coll_name="METADATA_PRED", query={"mobile": m})
        msg = f"DELETED {m} FROM METADATA_PRED"
        logger.info(msg)
        messages.append(msg)

    await mongo.upsert_documents_hashed(
        coll_name="METADATA_PRED", records=update_not_given_birth, id_fields=["mobile"]
    )

    msg = f"{len(update_not_given_birth)} RECORDS ADDED TO METADATA_PRED"
    logger.info(msg)
    messages.append(msg)

    return messages

    # ! Removed calculation of ga_entry, ga_exit, ga_last
    # record = {
    #     'date_joined': earliest.strftime("%Y-%m-%d"),
    #     'ga_entry': ga_entry,
    #     'ga_exit_add': ga_exit_add,
    #     'ga_exit_last': ga_exit_last,
    # }
    #
    # mobile_query_str    = ",".join([f"'{i}'" for i in new_not_given_birth])
    # measurements_df     = sql.query_to_dataframe(
    #         query=RECRUITED_PATIENTS_QUERY.format(
    #         start="'2025-03-01 00:00:00'",
    #         end=f"'{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'",
    #         numbers=mobile_query_str
    #     )
    # )
    # measurements_df     = measurements_df.sort_values(["mobile", "m_time"])
    # grouped_df          = measurements_df.groupby("mobile")
    # queried_mobile_set = set([mobile for mobile, _ in grouped_df])
    #
    # msg = f'[MySQL] {len(queried_mobile_set)} patients from MySQL'
    # print(msg) ; messages.append(msg)

    # patient_measurements_df = grouped_df.get_group(patient["mobile"])
    # earliest_iter = patient_measurements_df.iterrows() ; ga_entry_iter = patient_measurements_df.iterrows()
    #
    # # Get ADD (could be None)
    # add = f"{patient['add']} {patient['delivery_time']}" if patient["add"] else None
    #
    # # Get the earliest measurement (cannot be None)
    # earliest_idx, earliest_m = next(earliest_iter)
    # earliest = earliest_m['m_time']
    #
    # # Get the ga_entry for earliest measurement (cannot be None)
    # ga_entry_idx, ga_entry_m = next(ga_entry_iter)
    # basic_info_str  = ga_entry_m['basic_info']
    # conclusion_str  = ga_entry_m['conclusion'] if pd.notna(ga_entry_m['conclusion']) else None
    # ga_entry_temp   = extract_gest_age(conclusion_str, basic_info_str)
    #
    # # Get ga_entry (cannot be None)
    # ga_entry_mismatch = False
    # while ga_entry_temp is None:
    #
    #     ga_entry_mismatch = True
    #
    #     ga_entry_idx, ga_entry_m = next(ga_entry_iter)
    #
    #     basic_info_str  = ga_entry_m['basic_info']
    #     conclusion_str  = ga_entry_m['conclusion'] if pd.notna(ga_entry_m['conclusion']) else None
    #     ga_entry_temp   = extract_gest_age(conclusion_str, basic_info_str)
    #
    # if ga_entry_mismatch:
    #     ga_entry = ga_entry_temp - (ga_entry_m['m_time']-earliest).days
    # else:
    #     ga_entry = ga_entry_temp
    #
    # # Calculate ga_exit_add, ga_exit_last if ADD present ; Recalculate the earliest if needed
    # ga_exit_add = None ; ga_exit_last = None
    # if add is not None:
    #
    #     # Get Delivery Exit Time and Last Exit Time (None if ADD is None)
    #     exit_time_add   = datetime.strptime(add, "%Y-%m-%d %H:%M") if add else None
    #     exit_time_last  = patient_measurements_df['m_time'].iloc[-1] if add else None
    #
    #     # If the measurement date is too early (indicates previous pregnancy, and the earliest measurement is wrong)
    #     if (exit_time_add-earliest).days > 280:
    #
    #         msg = f"[Retry] {patient['mobile']}: Recalculate earliest measurement"
    #         print(msg) ; messages.append(msg)
    #
    #         # Recalculate the earliest measurement if the initial one was wrong
    #         while (exit_time_add-earliest).days > 280:
    #             earliest_idx, earliest_m = next(earliest_iter)
    #             earliest = earliest_m['m_time']
    #
    #         # Iterate until ga_entry and earliest meet
    #         while ga_entry_idx < earliest_idx:
    #             ga_entry_idx, ga_entry_m = next(ga_entry_iter)
    #         while earliest_idx < ga_entry_idx:
    #             earliest_idx, earliest_m = next(earliest_iter)
    #
    #         basic_info_str  = ga_entry_m['basic_info']
    #         conclusion_str  = ga_entry_m['conclusion'] if pd.notna(ga_entry_m['conclusion']) else None
    #         ga_entry_temp   = extract_gest_age(conclusion_str, basic_info_str)
    #
    #         ga_entry_mismatch = False
    #         while ga_entry_temp is None:
    #
    #             ga_entry_mismatch = True
    #
    #             ga_entry_idx, ga_entry_m = next(ga_entry_iter)
    #
    #             basic_info_str  = ga_entry_m['basic_info']
    #             conclusion_str  = ga_entry_m['conclusion'] if pd.notna(ga_entry_m['conclusion']) else None
    #             ga_entry_temp   = extract_gest_age(conclusion_str, basic_info_str)
    #
    #         if ga_entry_mismatch:
    #             ga_entry = ga_entry_temp - (ga_entry_m['m_time'] - earliest).days
    #         else:
    #             ga_entry = ga_entry_temp
    #
    #     # Get ga_exit_add, ga_exit_last
    #     ga_exit_add  = ga_entry + (exit_time_add-earliest).days
    #     ga_exit_last = ga_entry + (exit_time_last-earliest).days


async def historical(hist_df):

    logger.info(f"UPDATING METADATA_HIST: {st.session_state.mode}")

    cfg = get_cfg()
    sql = SQLDBConnector(SQL_CONFIG)
    mongo = MongoDBConnector(cfg)
    messages = []

    hist_df["mobile"] = hist_df["mobile"].astype(str)

    msg = f"{len(hist_df)} PATIENTS LOADED FROM historical_metadata.xlsx"
    logger.info(msg)
    messages.append(msg)

    hist_sql = sql.query_to_dataframe(query=HISTORICAL_METADATA_QUERY)

    hist_pivot = hist_sql.pivot(
        index=[
            i for i in hist_sql.columns if i not in ["record_type", "record_answer"]
        ],
        columns="record_type",
        values="record_answer",
    ).reset_index()

    msg = f"{len(hist_pivot)} HISTORICAL METADATA RECORDS FETCHED FROM NAVICAT"
    logger.info(msg)
    messages.append(msg)

    merged = hist_pivot.merge(hist_df, on="mobile", how="left")

    df = merged.copy()

    preg_count = df[1.0]
    had_preterm = df[8.0]
    had_surgery = df[13.0]
    gdm = df[4.0]
    pih = df[5.0]

    df["origin"] = "HIST"
    df["age"] = pd.to_numeric(df["age"], errors="coerce").astype("Int64")
    df["had_pregnancy"] = (preg_count > 1).astype(int)
    df["had_preterm"] = (had_preterm == 0).astype(int)
    df["had_surgery"] = (had_surgery == 0).astype(int)
    df["gdm"] = (gdm == 0).astype(int)
    df["pih"] = (pih == 0).astype(int)

    df["bmi"] = df.apply(
        lambda r: bmi_choose_weight_kg(
            height_cm=r["height"], weight_val=r["old_weight"]
        ),
        axis=1,
    )

    df["edd"] = df["expected_born_date"].apply(
        lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else None
    )

    df["add"] = df["add"].apply(
        lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else None
    )

    df["onset"] = df["onset"].apply(
        lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else None
    )

    df["end_born_ts"] = (
        pd.to_datetime(df["end_born_ts"], unit="s", utc=True)
        .dt.tz_convert("Asia/Singapore")
        .dt.strftime("%Y-%m-%d %H:%M")
    )

    has_delivery_info = (
        df["add"].notna() | df["onset"].notna() | df["delivery_type"].notna()
    )

    df.loc[~has_delivery_info, "add"] = df.loc[~has_delivery_info, "end_born_ts"]
    df.loc[~has_delivery_info, "onset"] = None
    df.loc[~has_delivery_info, "delivery_type"] = None

    df.drop(
        columns=[
            1.0,
            2.0,
            4.0,
            5.0,
            8.0,
            13.0,
            "height",
            "old_weight",
            "expected_born_date",
            "end_born_ts",
        ],
        inplace=True,
    )

    df.drop(columns=df.columns[df.columns.isna()], inplace=True)

    historical_metadata = df.to_dict(orient="records")

    await mongo.upsert_documents_hashed(
        coll_name="METADATA_HIST",
        records=historical_metadata,
        id_fields=["mobile"],
    )

    msg = f"{len(historical_metadata)} RECORDS ADDED TO METADATA_HIST"
    logger.info(msg)
    messages.append(msg)

    return messages

    # ! Removed calculation of ga_entry, ga_exit, ga_last
    # Get ga_entry time
    # basic_info_str  = row['basic_info']
    # conclusion_str  = row['conclusion'] if pd.notna(row['conclusion']) else None
    # ga_entry        = extract_gest_age(conclusion_str, basic_info_str)
    #
    # Get ga_exit time (ADD, last measurement)
    # entry_time      = row['earliest']
    # exit_time_add   = row['add']
    # exit_time_last  = row['latest']
    # ga_exit_add     = ga_entry + (exit_time_add - entry_time).days if pd.notna(exit_time_add) else None
    # ga_exit_last    = ga_entry + (exit_time_last - entry_time).days if pd.notna(exit_time_last) else None

    # record = {
    #     'origin'          : 'hist',
    #     'edd'           : row['edd'].strftime("%Y-%m-%d") if pd.notna(row['edd']) else None,
    #     'delivery_type' : row['delivery_type'],
    #     'add'           : row['add'].to_pydatetime().strftime("%Y-%m-%d %H:%M"),
    #     'onset'         : row['onset'].to_pydatetime().strftime("%Y-%m-%d %H:%M") if pd.notna(row['onset']) else None
    # }
