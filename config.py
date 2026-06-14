"""
实验配置常量
每只鼠 4 个伤口，每个伤口属于不同处理组
"""

# ==================== 鼠分组 ====================
# 不电刺激鼠 (8只)
NON_ES_RATS = [7, 9, 10, 11, 13, 15, 16, 17]
# 电刺激鼠 (9只)
ES_RATS = [1, 2, 3, 4, 5, 6, 8, 12, 14]

# 每只鼠的 4 个伤口对应的处理组
WOUND_MAPPING = {
    "non_es": {1: "Control", 2: "Alginate", 3: "Alginate_HJ", 4: "Alginate_HJ"},
    "es":     {1: "Pure_ES", 2: "Pure_ES", 3: "Stretched_HJ_ES", 4: "Stretched_HJ_ES"},
}

WOUND_COUNT = 4

# ==================== 所有组 ====================
GROUPS = ["Control", "Alginate", "Alginate_HJ", "Pure_ES", "Stretched_HJ_ES"]

GROUP_LABELS = {
    "Control":          "对照组",
    "Alginate":         "海藻酸钙组",
    "Alginate_HJ":      "海藻酸钙异质结组",
    "Pure_ES":          "纯电刺激组",
    "Stretched_HJ_ES":  "拉伸异质结水凝胶+电刺激组",
}

def get_rat_type(rat_id: int) -> str:
    if rat_id in ES_RATS:
        return "es"
    return "non_es"

def get_rat_type_label(rat_id: int) -> str:
    return "电刺激" if rat_id in ES_RATS else "不电刺激"

ALL_RATS = sorted(NON_ES_RATS + ES_RATS)  # 共17只

TOTAL_DAYS = 14

# ==================== 实验时间线 ====================
TIMELINE = {
    1:  ("—",   "造模日",            False),
    2:  ("d0",  "治疗开始",          False),
    3:  ("d1",  "治疗第1天",         False),
    4:  ("d2",  "治疗第2天",         False),
    5:  ("d3",  "治疗第3天·取材",    True),
    6:  ("d4",  "治疗第4天",         False),
    7:  ("d5",  "治疗第5天",         False),
    8:  ("d6",  "治疗第6天",         False),
    9:  ("d7",  "治疗第7天·取材",    True),
    10: ("d8",  "治疗第8天",         False),
    11: ("d9",  "治疗第9天",         False),
    12: ("d10", "治疗第10天",        False),
    13: ("d11", "治疗第11天",        False),
    14: ("d12", "最终取材日",        True),
}

SAMPLING_DAYS = {5, 9, 14}

# ==================== 样本类型 ====================
SAMPLE_TYPES = [
    "皮肤组织 (Skin)",
    "创面组织 (Wound bed)",
    "肝脏 (Liver)",
    "肾脏 (Kidney)",
    "脾脏 (Spleen)",
    "血清 (Serum)",
    "其他 (Other)",
]

FIXATION_METHODS = [
    "10% 福尔马林 (Formalin)",
    "RNA-later",
    "液氮速冻 (LN2 frozen)",
    "OCT 包埋 (OCT embedding)",
    "不固定 (Fresh)",
]
