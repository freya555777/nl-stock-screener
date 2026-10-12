# -*- coding: utf-8 -*-
"""
指标与条件模型（Schema）
=======================
定义：
1. 指标元数据：id、中文名、单位、所属类别、数值方向（越大越好/越小越好/中性）
2. 操作符：gt/ge/lt/le/between/pct_ge/pct_le
3. 预设意图模板：把"经营改善""估值合理"等模糊表达映射为可执行条件
4. 冲突识别规则：硬冲突（不可同时满足）与软冲突（互相制约，需用户确认）

说明：所有指标口径以本文件为准；百分比类指标 value 直接存百分数数值（如 20 表示 20%）。
"""

# ---------------- 指标元数据 ----------------
# higher_better: True=越大越好, False=越小越好, None=中性（取决于用户条件）
METRICS = {
    # 估值
    "pe_ttm":         {"label": "PE(TTM)",      "unit": "倍", "category": "估值", "higher_better": False, "desc": "市盈率（滚动12个月），亏损公司为负或缺失"},
    "pb":             {"label": "PB",           "unit": "倍", "category": "估值", "higher_better": False, "desc": "市净率"},
    "ps_ttm":         {"label": "PS(TTM)",      "unit": "倍", "category": "估值", "higher_better": False, "desc": "市销率（滚动12个月）"},
    "dividend_yield": {"label": "股息率",         "unit": "%",  "category": "估值", "higher_better": True,  "desc": "近12个月股息率（税前）"},
    "mkt_cap":        {"label": "总市值",         "unit": "亿元", "category": "估值", "higher_better": None, "desc": "总市值（亿元）"},

    # 成长
    "revenue_yoy":    {"label": "营收同比",       "unit": "%",  "category": "成长", "higher_better": True,  "desc": "最新报告期营业收入同比增速"},
    "profit_yoy":     {"label": "归母净利同比",   "unit": "%",  "category": "成长", "higher_better": True,  "desc": "最新报告期归母净利润同比增速"},
    "profit_cagr3":   {"label": "3年净利复合增速", "unit": "%",  "category": "成长", "higher_better": True,  "desc": "近3年归母净利润复合增速"},

    # 质量
    "gross_margin":   {"label": "毛利率",         "unit": "%",  "category": "质量", "higher_better": True,  "desc": "最新报告期销售毛利率"},
    "net_margin":     {"label": "净利率",         "unit": "%",  "category": "质量", "higher_better": True,  "desc": "最新报告期销售净利率"},
    "roe":            {"label": "ROE(加权)",     "unit": "%",  "category": "质量", "higher_better": True,  "desc": "最新报告期加权净资产收益率"},
    "debt_ratio":     {"label": "资产负债率",     "unit": "%",  "category": "质量", "higher_better": False, "desc": "最新报告期资产负债率"},
    "ocf_to_profit":  {"label": "经营现金流/净利", "unit": "倍", "category": "质量", "higher_better": True,  "desc": "经营现金流净额 / 归母净利润"},

    # 走势 / 波动
    "mom_20d":        {"label": "近20日涨幅",     "unit": "%",  "category": "走势", "higher_better": None, "desc": "近20个交易日区间涨跌幅"},
    "mom_60d":        {"label": "近60日涨幅",     "unit": "%",  "category": "走势", "higher_better": None, "desc": "近60个交易日区间涨跌幅"},
    "vol_20d":        {"label": "近20日年化波动率", "unit": "%", "category": "走势", "higher_better": False, "desc": "近20个交易日收益率年化波动率"},
    "drawdown_60d":   {"label": "近60日最大回撤", "unit": "%", "category": "走势", "higher_better": None, "desc": "近60个交易日最大回撤（负值，如 -18 表示回撤18%）"},

    # 资金 / 热度
    "turnover_20d":   {"label": "近20日平均换手率", "unit": "%", "category": "资金热度", "higher_better": None, "desc": "近20个交易日平均换手率"},
    "amount_20d":     {"label": "近20日日均成交额", "unit": "亿元", "category": "资金热度", "higher_better": None, "desc": "近20个交易日日均成交额（亿元）"},
    "hot_rank":       {"label": "热榜排名",        "unit": "名", "category": "资金热度", "higher_better": False, "desc": "同花顺热榜排名（越小越靠前）"},
}

# 操作符定义（percentile 类操作符在全市场/全池子中计算分位）
OPS = {
    "gt":      {"label": "大于", "n_values": 1, "desc": "指标值 > 阈值"},
    "ge":      {"label": "大于等于", "n_values": 1, "desc": "指标值 ≥ 阈值"},
    "lt":      {"label": "小于", "n_values": 1, "desc": "指标值 < 阈值"},
    "le":      {"label": "小于等于", "n_values": 1, "desc": "指标值 ≤ 阈值"},
    "between": {"label": "介于", "n_values": 2, "desc": "区间 [lo, hi]，闭区间"},
    "pct_ge":  {"label": "处于全池前", "n_values": 1, "desc": "指标在全股票池中的分位 ≥ 阈值（如 pct_ge 80 表示处于前20%分位）"},
    "pct_le":  {"label": "处于全池后", "n_values": 1, "desc": "指标在全股票池中的分位 ≤ 阈值（如 pct_le 30 表示处于后30%分位）"},
}

# ---------------- 预设意图模板 ----------------
# 规则解析器与 LLM 提示词共享同一套默认口径，保证两种解析方式结果一致、可解释
PRESET_INTENTS = {
    "经营改善": {
        "desc": "基本面改善：盈利与营收保持增长、ROE 不差",
        "conditions": [
            {"metric": "profit_yoy", "op": "ge", "value": 20},
            {"metric": "revenue_yoy", "op": "ge", "value": 10},
            {"metric": "roe", "op": "ge", "value": 10},
        ],
    },
    "估值合理": {
        "desc": "估值处于合理区间：正盈利且 PE/PB 不过高",
        "conditions": [
            {"metric": "pe_ttm", "op": "between", "value": [0, 40]},
            {"metric": "pb", "op": "between", "value": [0, 5]},
        ],
    },
    "走势稳定": {
        "desc": "波动可控、回撤不过深",
        "conditions": [
            {"metric": "vol_20d", "op": "le", "value": 35},
            {"metric": "drawdown_60d", "op": "ge", "value": -25},
        ],
    },
    "低估值": {
        "desc": "PE 处于全池后 30% 分位（默认口径）",
        "conditions": [
            {"metric": "pe_ttm", "op": "pct_le", "value": 30},
        ],
    },
    "高成长": {
        "desc": "归母净利同比 ≥ 30%",
        "conditions": [
            {"metric": "profit_yoy", "op": "ge", "value": 30},
        ],
    },
    "高ROE": {
        "desc": "ROE ≥ 15%",
        "conditions": [
            {"metric": "roe", "op": "ge", "value": 15},
        ],
    },
    "高股息": {
        "desc": "股息率 ≥ 3%",
        "conditions": [
            {"metric": "dividend_yield", "op": "ge", "value": 3},
        ],
    },
    "低波动": {
        "desc": "近20日年化波动率 ≤ 25%",
        "conditions": [
            {"metric": "vol_20d", "op": "le", "value": 25},
        ],
    },
    "强势股": {
        "desc": "近60日涨幅 ≥ 20%",
        "conditions": [
            {"metric": "mom_60d", "op": "ge", "value": 20},
        ],
    },
    "大盘蓝筹": {
        "desc": "总市值 ≥ 1000 亿且 ROE ≥ 12%",
        "conditions": [
            {"metric": "mkt_cap", "op": "ge", "value": 1000},
            {"metric": "roe", "op": "ge", "value": 12},
        ],
    },
    "小盘股": {
        "desc": "总市值 ≤ 100 亿",
        "conditions": [
            {"metric": "mkt_cap", "op": "le", "value": 100},
        ],
    },
    "热门股": {
        "desc": "热榜排名处于全池前 30%（即 pct_le 30）",
        "conditions": [
            {"metric": "hot_rank", "op": "pct_le", "value": 30},
        ],
    },
}

# 特殊条件类型（不在 METRICS 中的非指标型过滤）
SPECIAL_CONDITIONS = {
    "exclude_st": {
        "label": "剔除ST",
        "desc": "剔除 ST / *ST 股票（演示数据中 is_st 为演示口径标注）",
    },
    "industry_exclude": {
        "label": "排除行业",
        "value_type": "list",
        "desc": "排除指定二级行业（如 银行、地产）",
    },
}

# ---------------- 语义冲突规则 ----------------
# 硬冲突：两个条件无法同时满足（error）
# 软冲突：互相制约但并非必然矛盾（warning）
SEMANTIC_CONFLICTS = [
    # 同指标互斥区间
    {"level": "error", "desc": "同一指标设置了互斥区间"},
    # 大盘 vs 小盘
    {"level": "error", "match": ("大盘蓝筹", "小盘股"), "msg": "「大盘蓝筹」（市值≥1000亿）与「小盘股」（市值≤100亿）无法同时满足"},
    # 高成长 + 低波动（提示，不一定矛盾）
    {"level": "warning", "match": ("高成长", "低波动"), "msg": "「高成长」与「低波动」可能互斥：高成长股往往波动更大，请确认口径"},
    # 低估值 + 高成长（提示）
    {"level": "warning", "match": ("低估值", "高成长"), "msg": "「低估值」与「高成长」组合通常会显著缩小候选池，属正常"},
]

# 演示数据集的时间口径（财务指标为演示数据，行情字段可被实时行情覆盖）
DEMO_AS_OF = "2026-10-09"   # 财务/指标演示快照日期（最近交易日）
QUOTE_SOURCE_LABEL = "腾讯行情·实时"
DEMO_SOURCE_LABEL = "演示数据集（非真实财务数据，仅用于功能演示）"
