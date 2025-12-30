import os
import re
import pandas as pd

from config.configs import REMOTE_MONGO_CONFIG, TEST_MONGO_CONFIG
from database_manager.database.mongo import MongoDBConnector

mode = os.getenv("APP_MODE")

if mode == "test": cfg = TEST_MONGO_CONFIG
if mode == "remote": cfg = REMOTE_MONGO_CONFIG

AWARENESS_MAP = {"能感受/察觉": "Yes", "不能感受/察觉": "No"}

def find_col_name(cols, patterns):
    """
    Return the first column whose header matches ANY regex in `patterns`.
    """
    for pat in patterns:

        rx = re.compile(pat)

        for c in cols:

            if rx.search(c):
                return c

    print(f"No matching columns for {patterns}")

    return None

def safe_get_value(row, col, default=""):

    """
    Ensure that all values read are strings
    Ensure that null/none fields are still returned as empty strings
    """

    value = row.get(col, default)

    # Handle null values
    if pd.isna(value):
        return default

    return str(value).strip()

def strip_choice(val):
    """
    For MCQ/MRQ answers like 'A.是' or 'B.头晕', drop the letter+dot prefix
    and return only the text after the dot. Otherwise, return the trimmed value
    """

    # If empty string
    if not val:
        return ""

    # If '.' not in val, nothing to split
    elif "." not in val:
        return val

    else:
        _, rest = val.split(".", 1)
        return rest.strip()

def is_placeholder(text: str) -> bool:

    """
    True for values like: '其他', '其它', '其他____{...}', '其它________', '其他__________'
    """

    if not text:
        return True

    if "没有" in text:
        return True

    other_aliases = ("其他", "其它")

    if text in other_aliases:
        return True

    # "其他____{fillblank-xxxx}" or "其它________"
    if re.match(rf"^({'|'.join(other_aliases)})\s*(_+|\{{.*\}})\s*$", text):
        return True

    # "其他" followed only by punctuation/spaces
    if re.match(rf"^({'|'.join(other_aliases)})[\s\W]*$", text):
        return True

    return False

def collect_mrq_by_keywords(row, cols, group_keywords):
    """
    Generic multi-response collector
    - Picks columns whose header contains ALL keywords in `group_keywords`
    - Keeps ticked values (ignores '其他' placeholders)
    - Appends free-text from '[选项填空]' or raw '{fillblank-...}' columns when present
    """

    def header_in_group(h):
        return all(kw in h for kw in group_keywords)

    values          = []
    free_other      = ""

    # The one explicit free-text column ends with "[选项填空]"
    for c in cols:
        if header_in_group(c) and c.endswith("[选项填空]"):
            free_other = safe_get_value(row, c)

    # Normal MRQ ticked options
    for c in cols:

        if header_in_group(c) and not c.endswith("[选项填空]"):

            v = strip_choice(safe_get_value(row, c))

            if v and not is_placeholder(v):
                values.append(v)

    joined  = ", ".join(values)

    if free_other:
        joined = f"{joined}, {free_other}" if joined else free_other

    return joined

def parse_ga_str(ga_str):
    """
    Ensure that ga_str has format '{week}.{day}'
    For example, '38.4' means 38 weeks, 4 days
    Returns (original_str, total_days) or ("", None) if invalid
    """

    # Handle empty strings
    if not ga_str:
        return "", None

    if "." in ga_str:
        week_str, day_str = ga_str.split(".", 1)
        week = int(week_str) ; day = int(day_str)
    else:
        week = int(ga_str) ; day = 0

    day = max(0, min(6, day))

    return ga_str, week*7+day

#################### MAPPINGS ####################
def yes_no_mapping(text, default):

    if not text:
        return default

    if "否" in text:
        return "No"

    if "没有" in text:
        return "No"

    if "不是" in text:
        return "No"

    if "不会" in text:
        return "No"

    if "有" in text:
        return "Yes"

    if "是" in text:
        return "Yes"

    if "会" in text:
        return "Yes"

    print(f"{text} not valid, defaulting to 'Yes'")

    return "Yes"

def frequency_mapping(text, default):

    if not text:
        return default

    if "一" in text:
        return "1"

    if "二" in text or "两" in text:
        return "2"

    if "三" in text:
        return "3"

    if "四" in text:
        return "4"

    if "五" in text:
        return "5"

    if "六" in text:
        return ">=6"

    print(f"{text} not valid, defaulting to {default}")

    return default

async def upsert(df_pre, df_post):

    mongo       = MongoDBConnector(cfg)
    messages    = []

    ######################################## PRE-SURVEY ########################################

    cols = list(df_pre.columns)

    ga_now_col              = find_col_name(cols, [r".*4\.目前的孕周（例如 38\.4 代表38周4天）.*"])
    first_preg_col          = find_col_name(cols, [r".*11\.这是您第一次怀孕吗？.*"])
    num_preg_col            = find_col_name(cols, [r".*12\.\s*这是您第几次怀孕？（包括现在）.*"])
    first_deliv_col         = find_col_name(cols, [r".*13\.这是您第一次分娩吗？.*"])
    num_children_col        = find_col_name(cols, [r".*14\.您已经有几个孩子了？.*"])
    prev_preterm_col        = find_col_name(cols, [r".*16\.上一次怀孕有出现早产吗？.*"])
    smoke_hist_col          = find_col_name(cols, [r".*20\.您有抽烟习惯吗？.*"])
    still_smoke_col         = find_col_name(cols, [r".*21\.目前还在抽烟吗？.*"])
    quit_smoke_preg_col     = find_col_name(cols, [r".*22\.是怀孕后才戒的吗？.*"])
    alcohol_hist_col        = find_col_name(cols, [r".*23\.您有饮酒习惯吗？.*"])
    still_drink_col         = find_col_name(cols, [r".*24\.目前还在饮酒吗？.*"])
    quit_drink_preg_col     = find_col_name(cols, [r".*25\.是怀孕后才戒的吗？.*"])
    drug_hist_col           = find_col_name(cols, [r".*26\.您是否有药物或毒品滥用史？.*"])
    surgery_history_col     = find_col_name(cols, [r".*17\.您是否做过剖腹产或子宫相关手术？.*"])

    survey_date_col         = find_col_name(cols, [r".*开始答题时间.*"])
    name_col                = find_col_name(cols, [r".*1\.名字.*"])
    contact_col             = find_col_name(cols, [r".*2\.电话号码.*"])
    age_col                 = find_col_name(cols, [r".*3\.您的年龄是多少？.*"])
    height_col              = find_col_name(cols, [r".*5\.目前的身高（厘米）.*"])
    weight_col              = find_col_name(cols, [r".*6\.目前的体重（斤）.*"])
    pre_weight_col          = find_col_name(cols, [r".*7\.怀孕前的体重（斤）.*"])
    last_menstrual_col      = find_col_name(cols, [r".*8\.您的最后一次月经大概是什么时候？.*"])
    edd_col                 = find_col_name(cols, [r".*10\.预产期是？.*"])
    last_delivery_date_col  = find_col_name(cols, [r".*15\.最近一次分娩大概是什么时候？.*"])

    mapped_data_pre = []

    for _, row in df_pre.iterrows():

        ga_str, ga_days         = parse_ga_str(safe_get_value(row, ga_now_col))

        first_pregnancy_str     = safe_get_value(row, first_preg_col)
        first_pregnancy_cleaned = strip_choice(first_pregnancy_str)
        first_pregnancy         = yes_no_mapping(first_pregnancy_cleaned, "Yes")

        num_pregnancy_str       = safe_get_value(row, num_preg_col)
        num_pregnancy_cleaned   = strip_choice(num_pregnancy_str)
        num_pregnancy           = frequency_mapping(num_pregnancy_cleaned, "1")

        first_delivery_str      = safe_get_value(row, first_deliv_col)
        first_delivery_cleaned  = strip_choice(first_delivery_str)
        first_delivery          = yes_no_mapping(first_delivery_cleaned, "Yes")

        num_children_str        = safe_get_value(row, num_children_col)
        num_children_cleaned    = strip_choice(num_children_str)
        num_children            = frequency_mapping(num_children_cleaned, "0")

        prev_preterm_str        = safe_get_value(row, prev_preterm_col)
        prev_preterm_cleaned    = strip_choice(prev_preterm_str)
        prev_preterm            = yes_no_mapping(prev_preterm_cleaned, "NA")

        smoking_history_str     = safe_get_value(row, smoke_hist_col)
        smoking_history_cleaned = strip_choice(smoking_history_str)
        smoking_history         = yes_no_mapping(smoking_history_cleaned, "No")

        still_smoking_str       = safe_get_value(row, still_smoke_col)
        still_smoking_cleaned   = strip_choice(still_smoking_str)
        still_smoking           = yes_no_mapping(still_smoking_cleaned, "NA")

        quit_smoking_str        = safe_get_value(row, quit_smoke_preg_col)
        quit_smoking_cleaned    = strip_choice(quit_smoking_str)
        quit_smoking            = yes_no_mapping(quit_smoking_cleaned, "NA")

        alcohol_history_str     = safe_get_value(row, alcohol_hist_col)
        alcohol_history_cleaned = strip_choice(alcohol_history_str)
        alcohol_history         = yes_no_mapping(alcohol_history_cleaned, "No")

        still_drinking_str      = safe_get_value(row, still_drink_col)
        still_drinking_cleaned  = strip_choice(still_drinking_str)
        still_drinking          = yes_no_mapping(still_drinking_cleaned, "NA")

        quit_drinking_str       = safe_get_value(row, quit_drink_preg_col)
        quit_drinking_cleaned   = strip_choice(quit_drinking_str)
        quit_drinking           = yes_no_mapping(quit_drinking_cleaned, "NA")

        drug_history_str        = safe_get_value(row, drug_hist_col)
        drug_history_cleaned    = strip_choice(drug_history_str)
        drug_history            = yes_no_mapping(drug_history_cleaned, "No")

        surgery_history_str     = safe_get_value(row, surgery_history_col)
        surgery_history_cleaned = strip_choice(surgery_history_str)
        surgery_history         = yes_no_mapping(surgery_history_cleaned, "No")

        record = {
            "survey_date"           : safe_get_value(row, survey_date_col),
            "name"                  : safe_get_value(row, name_col),
            "mobile"                : safe_get_value(row, contact_col),
            "age"                   : safe_get_value(row, age_col),
            "curr_height"           : safe_get_value(row, height_col),
            "curr_weight"           : safe_get_value(row, weight_col),
            "pre_weight"            : safe_get_value(row, pre_weight_col),
            "last_menstrual"        : safe_get_value(row, last_menstrual_col),
            "edd"                   : safe_get_value(row, edd_col, default=""),
            "last_delivery"         : safe_get_value(row, last_delivery_date_col, default="NA"),
            "ga_now_str"            : ga_str,
            "ga_now"                : ga_days,
            "had_pregnancy"         : "Yes" if first_pregnancy == "No" else "No",
            "n_pregnancy"           : num_pregnancy,
            "had_delivery"          : "Yes" if first_delivery == "No" else "No",
            "n_children"            : num_children,
            "had_preterm"           : prev_preterm,
            "smoking_history"       : smoking_history,
            "still_smoking"         : still_smoking,
            "quit_smoking"          : quit_smoking,
            "alcohol_history"       : alcohol_history,
            "still_drinking"        : still_drinking,
            "quit_drinking"         : quit_drinking,
            "drug_history"          : drug_history,
            "had_surgery"           : surgery_history
        }

        symptoms_prefix     = "18.您现在有没有以下不适？"
        diagnosed_prefix    = "19.此次怀孕期间，医生是否诊断以下疾病？"

        symptoms_list = [] ; diagnosed_list = []
        for col in row.index:

            if col.startswith(symptoms_prefix):
                symptom = safe_get_value(row, col)
                symptom_cleaned = strip_choice(symptom)
                if not is_placeholder(symptom_cleaned):
                    symptoms_list.append(symptom_cleaned)

            if col.startswith(diagnosed_prefix):
                diagnosed = safe_get_value(row, col)
                diagnosed_cleaned = strip_choice(diagnosed)
                if not is_placeholder(diagnosed_cleaned):
                    diagnosed_list.append(diagnosed_cleaned)

        all_symptoms    = ", ".join(symptoms_list)
        all_diagnosed   = ", ".join(diagnosed_list)

        record['pregnancy_symptoms']    = all_symptoms
        record['diagnosed_conditions']  = all_diagnosed

        mapped_data_pre.append(record)

    pre_contact_set = set() ; pre_unique_records = []
    for record in mapped_data_pre:

        contact_number = record.get("mobile")

        if not contact_number:
            txt = f"[Pre] Invalid contact number"
            print(txt)
            messages.append(txt)
            continue

        if contact_number in pre_contact_set:
            txt = f"[Pre] Repeated survey response for {contact_number}"
            print(txt)
            messages.append(txt)
            continue

        pre_contact_set.add(contact_number)
        pre_unique_records.append(record)

    await mongo.upsert_documents_hashed(
        coll_name="PRE_SURVEY",
        records=pre_unique_records,
        id_fields=["mobile"]
    )

    ######################################## POST-SURVEY ########################################

    cols = list(df_post.columns)

    name_col    = find_col_name(cols, [r"姓名"])
    contact_col = find_col_name(cols, [r"手机.?号码|联系方式|联系电话"])
    ga_exit_col = find_col_name(cols, [r"分娩时.*孕周.*第几周.*几天|孕周.*例如.*38.*周|孕周"])

    # Delivery related
    hosp_date_col           = find_col_name(cols, [r"什么时候.*住院|住院.*准备分娩"])
    delivery_type_col       = find_col_name(cols, [r"分娩方式"])
    add_col                 = find_col_name(cols, [r"实际.*分娩.*日期"])
    add_time_col            = find_col_name(cols, [r"实际.*分娩.*时间.*几点|实际.*分娩.*时间"])
    water_break_col         = find_col_name(cols, [r"羊水.*(什么.*时候|日期|时间).*破"])
    csect_datetime_col      = find_col_name(cols, [r"剖(腹|宫)产.*几点.*进入.*产房"])
    csect_reason_col        = find_col_name(cols, [r"剖(腹|宫)产.*因为什么原因|剖.*产.*原因"])
    dur_contr_to_birth_col  = find_col_name(cols, [r"从开始.*宫缩.*到.*出生.*持续.*多长.*时间"])
    dur_room_to_birth_col   = find_col_name(cols, [r"从进入.*产房.*到.*出生.*多长.*时间"])
    dur_inform_to_room_col  = find_col_name(cols, [r"从.*被告知.*进入.*产程.*到.*转入.*产房.*间隔.*多久"])

    # Usage related
    usage_reason_col    = find_col_name(cols, [r"使用.*主要.*目的|使用.*目的"])
    awareness_col       = find_col_name(cols, [r"使用.*期间.*(感受到|察觉).*(宫缩|收缩).*逐渐加剧"])
    influence_col       = find_col_name(cols, [r"(读数|数据).*(是否|有无).*(去医院|生产).*产生.*影响"])
    usefulness_col      = find_col_name(cols, [r"使用.*是否.*有助.*(监测|了解).*宝宝.*健康"])
    any_problems_col    = find_col_name(cols, [r"使用.*是否.*遇到过问题"])
    problems_desc_col   = find_col_name(cols, [r"简要描述.*遇到.*问题|问题.*描述"])
    will_recommend_col  = find_col_name(cols, [r"会.*推荐|是否.*推荐"])
    recommend_col       = find_col_name(cols, [r"为什么.*会.*推荐"])
    not_recommend_col   = find_col_name(cols, [r"为什么.*不会.*推荐"])
    ultrasound_col      = find_col_name(cols, [r"(医院|同时).*(胎儿|胎).*监护|CTG"])
    informed_doc_col    = find_col_name(cols, [r"是否.*告诉.*医生.*使用.*萌动|是否.*告知.*医生"])
    doc_reaction_col    = find_col_name(cols, [r"(他们|医生).*(什么).*反应|医生.*反应"])
    improvement_col     = find_col_name(cols, [r"认为.*可以.*改进|改进.*地方|改进.*建议"])

    mapped_data_post = []

    for _, row in df_post.iterrows():

        ga_str, ga_days = parse_ga_str(safe_get_value(row, ga_exit_col))

        awareness_str       = safe_get_value(row, awareness_col)
        awareness_cleaned   = strip_choice(awareness_str)
        awareness           = AWARENESS_MAP.get(awareness_cleaned)

        influence_str       = safe_get_value(row, influence_col)
        influence_cleaned   = strip_choice(influence_str)
        influence           = yes_no_mapping(influence_cleaned, "Yes")

        usefulness_str      = safe_get_value(row, usefulness_col)
        usefulness_cleaned  = strip_choice(usefulness_str)
        usefulness          = yes_no_mapping(usefulness_cleaned, "Yes")

        had_problems_str     = safe_get_value(row, any_problems_col)
        had_problems_cleaned = strip_choice(had_problems_str)
        had_problems         = yes_no_mapping(had_problems_cleaned, "No")

        will_recommend_str      = safe_get_value(row, will_recommend_col)
        will_recommend_cleaned  = strip_choice(will_recommend_str)
        will_recommend          = yes_no_mapping(will_recommend_cleaned, "Yes")

        had_ultrasound_str      = safe_get_value(row, ultrasound_col)
        had_ultrasound_cleaned  = strip_choice(had_ultrasound_str)
        ultrasound              = yes_no_mapping(had_ultrasound_cleaned, "Yes")

        informed_doc_str        = safe_get_value(row, informed_doc_col)
        informed_doc_cleaned    = strip_choice(informed_doc_str)
        informed_doctor         = yes_no_mapping(informed_doc_cleaned, "Yes")

        record = {
            "name"          : safe_get_value(row, name_col),
            "mobile"        : safe_get_value(row, contact_col),
            "ga_exit_str"   : ga_str,
            "ga_exit"       : ga_days,

            # Delivery related
            "hospitalised_date"         : safe_get_value(row, hosp_date_col),
            "delivery_type"             : strip_choice(safe_get_value(row, delivery_type_col)),
            "add"                       : safe_get_value(row, add_col),
            "delivery_time"             : safe_get_value(row, add_time_col),
            "water_break_datetime"      : safe_get_value(row, water_break_col),
            "c_section_datetime"        : safe_get_value(row, csect_datetime_col),
            "c_section_reason"          : safe_get_value(row, csect_reason_col),
            "duration_contr_to_birth"   : safe_get_value(row, dur_contr_to_birth_col),
            "duration_room_to_birth"    : safe_get_value(row, dur_room_to_birth_col),
            "duration_informed_to_room" : safe_get_value(row, dur_inform_to_room_col),

            # Usage related
            "usage_reason"          : safe_get_value(row, usage_reason_col),
            "awareness"             : awareness,
            "influence"             : influence,
            "usefulness"            : usefulness,
            "had_problems"          : had_problems,
            "problems_desc"         : safe_get_value(row, problems_desc_col),
            "will_recommend"        : will_recommend,
            "reasons_recommend"     : safe_get_value(row, recommend_col),
            "reasons_not_recommend" : safe_get_value(row, not_recommend_col),
            "had_ultrasound"        : ultrasound,
            "informed_doctor"       : informed_doctor,
            "doctor_reaction"       : safe_get_value(row, doc_reaction_col),
            "improvement"           : safe_get_value(row, improvement_col)
        }

        advantage_prefix    = "18.使用萌动设备时，您认为其主要优点有哪些？"
        disadvantage_prefix = "19.在使用萌动设备时，您认为存在哪些不足之处？"

        advantages_list = [] ; disadvantages_list = []
        for col in row.index:

            if col.startswith(advantage_prefix):
                adv = safe_get_value(row, col)
                adv_cleaned = strip_choice(adv)
                if not is_placeholder(adv_cleaned):
                    advantages_list.append(adv_cleaned)

            if col.startswith(disadvantage_prefix):
                disadv = safe_get_value(row, col)
                disadv_cleaned = strip_choice(disadv)
                if not is_placeholder(disadv_cleaned):
                    disadvantages_list.append(disadv_cleaned)

        advantages_str      = ", ".join(advantages_list)
        disadvantages_str   = ", ".join(disadvantages_list)

        record['advantages']    = advantages_str
        record['disadvantages'] = disadvantages_str

        mapped_data_post.append(record)

    post_contact_set = set() ; post_unique_records = []
    for record in mapped_data_post:

        contact_number = record.get("mobile")

        if not contact_number:
            continue

        if contact_number in post_contact_set:
            txt = f"[Post] Repeated survey response for {contact_number}"
            print(txt)
            messages.append(txt)
            continue

        post_contact_set.add(contact_number)
        post_unique_records.append(record)

    await mongo.upsert_documents_hashed(
        coll_name="POST_SURVEY",
        records=post_unique_records,
        id_fields=["mobile"]
    )

    print(f"Upserted {len(pre_unique_records)} records into MongoDB collection 'PRE_SURVEY'")
    print(f"Upserted {len(post_unique_records)} records into MongoDB collection 'POST_SURVEY'")

    return messages