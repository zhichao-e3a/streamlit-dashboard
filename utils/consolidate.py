import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Any, Optional

from config.configs import REMOTE_MONGO_CONFIG, TEST_MONGO_CONFIG, SQL_CONFIG
from database_manager.database.mongo import MongoDBConnector
from database_manager.database.mysql import SQLDBConnector
from database_manager.database.queries import RECRUITED_PATIENTS_QUERY, HISTORICAL_PATIENTS_QUERY

mode = os.getenv("APP_MODE")

if mode == "test": cfg = TEST_MONGO_CONFIG
if mode == "remote": cfg = REMOTE_MONGO_CONFIG

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
            print(e)
            return None

    h_cm = pd.to_numeric(height_cm, errors="coerce")
    w = _try_float(weight_val)
    if pd.isna(h_cm) or h_cm <= 0 or w is None:
        return None

    h_m = h_cm / 100.0
    kg_if_kg = w
    kg_if_jin = w * 0.5

    def _bmi(kg: Optional[float]) -> Optional[float]:
        return (kg / (h_m ** 2)) if (kg and h_m > 0) else None

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

def extract_gest_age(conclusion : str, basic_info : str) -> Optional[int]:

    gest_age        = None
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

    sql      = SQLDBConnector(SQL_CONFIG)
    mongo    = MongoDBConnector(cfg)
    messages = []

    pre_docs = await mongo.get_all_documents(
        "PRE_SURVEY",
        projection = {
            "_id"                   : 0,
            "name"                  : 1,
            "mobile"                : 1,
            "age"                   : 1,
            "curr_height"           : 1,
            "pre_weight"            : 1,
            "edd"                   : 1,
            "had_pregnancy"         : 1,
            "had_preterm"           : 1,
            "had_surgery"           : 1,
            "diagnosed_conditions"  : 1,
        }
    )

    post_docs = await mongo.get_all_documents(
        "POST_SURVEY",
        projection = {
            "_id"                   : 0,
            "mobile"                : 1,
            "delivery_type"         : 1,
            "add"                   : 1,
            "delivery_time"         : 1,
            "water_break_datetime"  : 1
        }
    )

    pre = pd.DataFrame(pre_docs) ; post = pd.DataFrame(post_docs)

    mobile_query_str    = ",".join([f"'{i['mobile']}'" for i in pre_docs])
    measurements_df     = sql.query_to_dataframe(query=RECRUITED_PATIENTS_QUERY.format(mobile_query_str=mobile_query_str))
    measurements_df     = measurements_df.sort_values(["mobile", "m_time"])
    grouped_df          = measurements_df.groupby("mobile")

    """
    Not all patients in pre-survey will be present in database
    Patients that will not be queried:
    - Did not register on Modoo (no patient data -> no measurement data)
    - Did not use Modoo products (no measurement data)
    """
    queried_mobile_set = set([mobile for mobile, _ in grouped_df])

    msg = f"[Mongo] {len(pre_docs)} pre-survey records"
    print(msg) ; messages.append(msg)

    msg = f"[Mongo] {len(post_docs)} post-survey records"
    print(msg) ; messages.append(msg)

    for d in pre_docs:

        if d['mobile']  not in queried_mobile_set:
            print(f"[MySQL] {d['mobile']}: Not registered on Modoo / No measurement data")

    msg = f'[MySQL] {len(queried_mobile_set)} patients from MySQL'
    print(msg) ; messages.append(msg)

    merged = pre.merge(post, on="mobile", how="left")
    merged.replace({np.nan: None}, inplace=True)

    new_records = []
    for _, patient in merged.iterrows():

        mobile = patient["mobile"]
        if mobile not in queried_mobile_set:
            continue

        patient_measurements_df = grouped_df.get_group(patient["mobile"])
        earliest_iter = patient_measurements_df.iterrows() ; ga_entry_iter = patient_measurements_df.iterrows()

        # Get ADD (could be None)
        add = f"{patient['add']} {patient['delivery_time']}" if patient["add"] else None

        # Get the earliest measurement (cannot be None)
        earliest_idx, earliest_m = next(earliest_iter)
        earliest = earliest_m['m_time']

        # Get the ga_entry for earliest measurement (cannot be None)
        ga_entry_idx, ga_entry_m = next(ga_entry_iter)
        basic_info_str  = ga_entry_m['basic_info']
        conclusion_str  = ga_entry_m['conclusion'] if pd.notna(ga_entry_m['conclusion']) else None
        ga_entry_temp   = extract_gest_age(conclusion_str, basic_info_str)

        # Get ga_entry (cannot be None)
        ga_entry_mismatch = False
        while ga_entry_temp is None:

            ga_entry_mismatch = True

            ga_entry_idx, ga_entry_m = next(ga_entry_iter)

            basic_info_str  = ga_entry_m['basic_info']
            conclusion_str  = ga_entry_m['conclusion'] if pd.notna(ga_entry_m['conclusion']) else None
            ga_entry_temp   = extract_gest_age(conclusion_str, basic_info_str)

        if ga_entry_mismatch:
            ga_entry = ga_entry_temp - (ga_entry_m['m_time']-earliest).days
        else:
            ga_entry = ga_entry_temp

        # Calculate ga_exit_add, ga_exit_last if ADD present ; Recalculate the earliest if needed
        ga_exit_add = None ; ga_exit_last = None
        if add is not None:

            # Get Delivery Exit Time and Last Exit Time (None if ADD is None)
            exit_time_add   = datetime.strptime(add, "%Y-%m-%d %H:%M") if add else None
            exit_time_last  = patient_measurements_df['m_time'].iloc[-1] if add else None

            # If the measurement date is too early (indicates previous pregnancy, and the earliest measurement is wrong)
            if (exit_time_add-earliest).days > 280:

                msg = f"[Retry] {mobile}: Recalculate earliest measurement"
                print(msg) ; messages.append(msg)

                # Recalculate the earliest measurement if the initial one was wrong
                while (exit_time_add-earliest).days > 280:
                    earliest_idx, earliest_m = next(earliest_iter)
                    earliest = earliest_m['m_time']

                # Iterate until ga_entry and earliest meet
                while ga_entry_idx < earliest_idx:
                    ga_entry_idx, ga_entry_m = next(ga_entry_iter)
                while earliest_idx < ga_entry_idx:
                    earliest_idx, earliest_m = next(earliest_iter)

                basic_info_str  = ga_entry_m['basic_info']
                conclusion_str  = ga_entry_m['conclusion'] if pd.notna(ga_entry_m['conclusion']) else None
                ga_entry_temp   = extract_gest_age(conclusion_str, basic_info_str)

                ga_entry_mismatch = False
                while ga_entry_temp is None:

                    ga_entry_mismatch = True

                    ga_entry_idx, ga_entry_m = next(ga_entry_iter)

                    basic_info_str  = ga_entry_m['basic_info']
                    conclusion_str  = ga_entry_m['conclusion'] if pd.notna(ga_entry_m['conclusion']) else None
                    ga_entry_temp   = extract_gest_age(conclusion_str, basic_info_str)

                if ga_entry_mismatch:
                    ga_entry = ga_entry_temp - (ga_entry_m['m_time'] - earliest).days
                else:
                    ga_entry = ga_entry_temp

            # Get ga_exit_add, ga_exit_last
            ga_exit_add  = ga_entry + (exit_time_add-earliest).days
            ga_exit_last = ga_entry + (exit_time_last-earliest).days

        record = {
            'origin'          : 'rec',
            'date_joined'   : earliest.strftime("%Y-%m-%d"),
            'name'          : patient['name'] if pd.notna(patient['name']) else None,
            'mobile'        : patient['mobile'],
            'age'           : int(patient['age']) if pd.notna(patient['age']) else None,
            'ga_entry'      : ga_entry,
            'ga_exit_add'   : ga_exit_add,
            'ga_exit_last'  : ga_exit_last,# if ga_exit_last <= ga_exit_add else ga_exit_add,
            'bmi'           : bmi_choose_weight_kg(patient['curr_height'], patient['pre_weight']),
            'edd'           : patient['edd'] if patient['edd'] else None,
            'had_pregnancy' : 1 if patient['had_pregnancy'] == 'Yes' else 0,
            'had_preterm'   : 1 if patient['had_preterm'] == 'Yes' else 0,
            'had_surgery'   : 1 if patient['had_surgery'] == 'Yes' else 0,
            'gdm'           : flag_contains_1_0(patient['diagnosed_conditions'], "妊娠糖尿病"),
            'pih'           : flag_contains_1_0(patient['diagnosed_conditions'], "妊娠高血压"),
            'delivery_type' : delivery_type_map(patient['delivery_type']),
            'add'           : add,
            'onset'         : compute_onset(patient) if add else None
        }

        new_records.append(record)

        await mongo.upsert_documents_hashed(
            coll_name="PATIENTS_UNIFIED",
            records=new_records,
            id_fields = ["mobile"]
        )

    msg = f"Recruited: {len(new_records)} consolidated patients upserted"
    print(msg) ; messages.append(msg)

    return messages

async def historical(hist_df):

    sql         = SQLDBConnector(SQL_CONFIG)
    mongo       = MongoDBConnector(cfg)
    messages    = []

    hist_df['mobile'] = hist_df['mobile'].astype(str)

    msg = f"[Excel] {len(hist_df)} patients loaded"
    print(msg) ; messages.append(msg)

    mobile_query_str = ",".join([f"'{i}'" for i in hist_df["mobile"].tolist()])

    hist_sql = sql.query_to_dataframe(query=HISTORICAL_PATIENTS_QUERY.format(mobile_query_str=mobile_query_str))

    msg = f"[MySQL] {len(hist_sql)} measurements fetched"
    print(msg) ; messages.append(msg)

    hist_pivot = hist_sql.pivot(
        index=[i for i in hist_sql.columns if i not in ['record_type', 'record_answer']],
        columns='record_type',
        values='record_answer'
    ).reset_index()

    msg = f"[MySQL] {len(hist_pivot)} patients fetched"
    print(msg) ; messages.append(msg)

    merged = hist_df.merge(hist_pivot, on='mobile', how='left')

    new_records = []
    for _, row in merged.iterrows():

        # Get ga_entry time
        basic_info_str  = row['basic_info']
        conclusion_str  = row['conclusion'] if pd.notna(row['conclusion']) else None
        ga_entry        = extract_gest_age(conclusion_str, basic_info_str)

        # Get ga_exit time (ADD, last measurement)
        entry_time      = row['earliest']
        exit_time_add   = row['add']
        exit_time_last  = row['latest']
        ga_exit_add     = ga_entry + (exit_time_add - entry_time).days if pd.notna(exit_time_add) else None
        ga_exit_last    = ga_entry + (exit_time_last - entry_time).days if pd.notna(exit_time_last) else None

        # 0='0 pregnancies', 1='1 pregnancies', 2='2 pregnancies', 3='>2 pregnancies'
        # Count current pregnancy as well so treat 0 and 1 as same
        preg_count  = row[1.0]
        # 0='有', 1='无', 2='未知'
        had_misc    = row[2.0]
        gdm         = row[4.0]
        pih         = row[5.0]
        had_preterm = row[8.0]
        had_surgery = row[13.0]

        bmi = bmi_choose_weight_kg(
            height_cm = row['height'],
            weight_val = row['old_weight']
        )

        record = {
            'origin'          : 'hist',
            # 'date_joined'   : row['reg_time'].to_pydatetime().strftime("%Y-%m-%d"),
            'date_joined'   : entry_time.strftime('%Y-%m-%d'),
            'name'          : row['name'] if pd.notna(row['name']) else None,
            'mobile'        : row['mobile'],
            'age'           : int(row['age']) if pd.notna(row['age']) else None,
            'ga_entry'      : ga_entry,
            'ga_exit_add'   : ga_exit_add,
            'ga_exit_last'  : ga_exit_last if ga_exit_last <= ga_exit_add else ga_exit_add,
            'bmi'           : bmi if pd.notna(bmi) else None,
            'edd'           : row['edd'].strftime("%Y-%m-%d") if pd.notna(row['edd']) else None,
            'had_pregnancy' : 1 if (preg_count > 1) else 0,
            'had_preterm'   : 1 if had_preterm == 0 else 0,
            'had_surgery'   : 1 if had_surgery == 0 else 0,
            'gdm'           : 1 if gdm == 0 else 0,
            'pih'           : 1 if pih == 0 else 0,
            'delivery_type' : row['delivery_type'],
            'add'           : row['add'].to_pydatetime().strftime("%Y-%m-%d %H:%M"),
            'onset'         : row['onset'].to_pydatetime().strftime("%Y-%m-%d %H:%M") if pd.notna(row['onset']) else None
        }

        new_records.append(record)

        await mongo.upsert_documents_hashed(
            coll_name='PATIENTS_UNIFIED',
            records=new_records,
            id_fields=['mobile']
        )

    msg = f"Historical: {len(new_records)} consolidated patients upserted"
    print(msg) ; messages.append(msg)

    return messages