# -*- coding: utf-8 -*-
"""
自然语言解析层（NL Parser）
==========================
把用户的模糊选股意图转成结构化条件（conditions + 意图标签 + 澄清项 + 缺失维度）。
双通道：
1. LLM 通道（配置 LLM_API_KEY / LLM_MODEL 后启用，更强模糊表达理解）
2. 规则通道（零依赖回退，覆盖题目示例句与常见句式）

输出统一 JSON，随后交由确定性筛选引擎执行——AI 只负责"理解"，不负责"判断"。
"""
import re

import demo_data
from demo_data import INDUSTRIES
import llm_client
from engine import validate_conditions, detect_conflicts, human_condition
from schema import METRICS, OPS, PRESET_INTENTS, SPECIAL_CONDITIONS

# 已支持指标的中文别名 → metric id（用于规则解析）
_METRIC_ALIASES = [
    (re.compile(r"市盈率|PE", re.I), "pe_ttm"),
    (re.compile(r"市净率|PB", re.I), "pb"),
    (re.compile(r"市销率|PS", re.I), "ps_ttm"),
    (re.compile(r"股息率|分红率|分红", re.I), "dividend_yield"),
    (re.compile(r"总市值|市值", re.I), "mkt_cap"),
    (re.compile(r"营收|收入", re.I), "revenue_yoy"),
    (re.compile(r"归母净利|净利润|净利|利润|业绩", re.I), "profit_yoy"),
    (re.compile(r"净资产收益率|ROE", re.I), "roe"),
    (re.compile(r"毛利率", re.I), "gross_margin"),
    (re.compile(r"年化波动率|波动率|波动", re.I), "vol_20d"),
    (re.compile(r"最大回撤|回撤", re.I), "drawdown_60d"),
    (re.compile(r"换手率", re.I), "turnover_20d"),
    (re.compile(r"成交额", re.I), "amount_20d"),
    (re.compile(r"热榜|热度|排名", re.I), "hot_rank"),
]

# 涨幅类：天数 → 指标
_MOM_DAYS = {20: "mom_20d", 60: "mom_60d"}

# 预设意图关键词（按"更长短语优先"匹配）
_PRESET_KEYWORDS = [
    ("经营改善", ["经营改善", "业绩改善", "基本面改善", "经营向好", "业绩向好"]),
    ("估值合理", ["估值合理", "估值不高", "估值正常", "价格合理", "合理估值"]),
    ("走势稳定", ["走势稳定", "走势相对稳定", "走势稳健", "股价稳定", "走势平稳"]),
    ("低估值", ["低估值", "估值低", "低估", "便宜"]),
    ("高成长", ["高成长", "高增长", "成长性好", "成长股", "成长性"]),
    ("高ROE", ["高ROE", "ROE高", "净资产收益率高", "高roe"]),
    ("高股息", ["高股息", "股息率高", "分红高", "分红好", "高分红"]),
    ("低波动", ["低波动", "波动低", "波动小"]),
    ("强势股", ["强势", "强势股", "走强", "趋势好"]),
    ("大盘蓝筹", ["大盘", "蓝筹", "龙头", "权重"]),
    ("小盘股", ["小盘", "小市值"]),
    ("热门股", ["热门", "热度高", "热榜"]),
]

# 当前版本暂不支持的维度（出现在输入时给出提示，不静默忽略）
_UNSUPPORTED = ["北向资金", "机构持仓", "龙虎榜", "融资余额", "质押", "解禁",
                "公告", "新闻", "情绪", "政策", "MACD", "KDJ", "金叉", "死叉"]

# 剔除ST
_ST_RE = re.compile(r"(剔除|排除|不要|去掉|避开|不选|过滤)\s*(ST|风险警示)", re.I)


class ParseError(ValueError):
    """解析失败（message 面向用户）。"""


# ---------------------------------------------------------------- 规则解析

def _split_segments(text: str):
    parts = re.split(r"[，。；、,;]+|且|并且|同时|还要|再要|另外", text)
    return [p.strip() for p in parts if p.strip()]


def _extract_compare(text: str):
    """在片段中提取 比较符+数值 → (op, value) 或 None。处理 between / 单值。"""
    m = re.search(r"(?:在|介于)?\s*([+-]?\d+(?:\.\d+)?)\s*(?:到|至|和|与|~|－|-)\s*([+-]?\d+(?:\.\d+)?)\s*(?:之间|以内|区间)?", text)
    if m:
        return "between", [float(m.group(1)), float(m.group(2))]
    m = re.search(r"(大于|超过|高于|不低于|至少|≥|>|小于|低于|不超过|不高于|不多于|少于|≤|<)\s*([+-]?\d+(?:\.\d+)?)", text)
    if not m:
        return None
    word, num = m.group(1), float(m.group(2))
    if word in ("大于", "超过", "高于", ">", "≥", "不低于", "至少"):
        op = "ge" if word in ("≥", "不低于", "至少") else "gt"
    else:
        op = "le" if word in ("≤", "不超过", "不高于", "不多于") else "lt"
    return op, num


def _strip_unit(s: str):
    return s.replace("%", "").replace("倍", "").replace("元", "").replace("亿元", "").replace("亿", "")


def _handle_drawdown(op, value):
    """回撤语义：'回撤不超过X%' → drawdown ≥ -X；'回撤大于X%' → drawdown < -X。"""
    if op in ("le", "lt"):
        return "ge", -abs(value)
    return "lt", -abs(value)


def _rule_parse(text: str, llm_note: str = None) -> dict:
    conditions = []
    tags = []
    clarifications = []
    missing_data = []
    industry_excludes = []  # 跨片段合并为一个「排除行业」条件
    seen = set()

    def add(cond):
        key = repr(cond)
        if key not in seen:
            seen.add(key)
            conditions.append(cond)

    for seg in _split_segments(text):
        low = seg.lower()
        # ---- 预设意图（先于数值规则，保证默认口径一致）----
        for tag, keys in _PRESET_KEYWORDS:
            if tag in tags:
                continue
            if any(k.lower() in low for k in keys):
                tags.append(tag)
                for c in PRESET_INTENTS[tag]["conditions"]:
                    add(c)
                clarifications.append(
                    f"「{tag}」已按默认口径解释：{PRESET_INTENTS[tag]['desc']}。可在条件面板修改。")
        # ---- 剔除 ST ----
        if _ST_RE.search(seg):
            add({"type": "exclude_st"})
            clarifications.append("已按演示口径添加「剔除 ST」条件。")
        # ---- 排除行业（收集片段内所有命中的行业，跨片段合并为一个条件）----
        matched_inds = [ind for ind in INDUSTRIES
                        if ind in seg and re.search(r"(排除|剔除|不要|避开|不选|不买)", seg)]
        industry_excludes.extend(matched_inds)
        if not matched_inds:
            for sector in sorted({s["sector"] for s in demo_data.UNIVERSE}):
                if sector in seg and re.search(r"(排除|剔除|不要|避开|不选|不买)", seg):
                    missing_data.append(f"「{sector}」为一级板块，当前版本仅支持按二级行业排除（如 银行、地产），该条件已忽略。")
                    break
        # ---- 数值条件 ----
        for rx, metric in _METRIC_ALIASES:
            m = rx.search(seg)
            if not m:
                continue
            cmp = _extract_compare(seg[m.end():])
            if not cmp:
                # 无比较符：尝试"XX前N"/"XX超过N%" 无比较词的表达，跳过并提示
                continue
            op, value = cmp
            # 处理万亿单位（市值）
            if metric == "mkt_cap":
                tw = re.search(r"(\d+(?:\.\d+)?)\s*万亿", seg)
                if tw and float(tw.group(1)) == value:
                    value *= 10000
            if metric == "drawdown_60d":
                op, value = _handle_drawdown(op, value)
            if op == "between":
                add({"metric": metric, "op": op, "value": [value[0], value[1]]})
            else:
                add({"metric": metric, "op": op, "value": value})
        # ---- 日涨幅 ----
        dm = re.search(r"(?:近)?(\d{1,3})日(?:涨幅|涨跌幅)", seg)
        if dm:
            days = int(dm.group(1))
            if days in _MOM_DAYS:
                cmp = _extract_compare(seg[dm.end():])
                if cmp and cmp[0] != "between":
                    add({"metric": _MOM_DAYS[days], "op": cmp[0], "value": cmp[1]})
            else:
                missing_data.append(f"「{days}日涨幅」暂不支持（已支持 20/60 日），该条件已忽略。")
        # ---- 不要亏损 / 盈利 ----
        if re.search(r"(不亏|剔除亏损|不要亏损|盈利)", seg) and not any(c.get("metric") == "profit_yoy" for c in conditions):
            add({"metric": "profit_yoy", "op": "gt", "value": 0})
            clarifications.append("「不亏损」按 归母净利同比 > 0 解释。")

    # 合并排除行业条件
    if industry_excludes:
        add({"type": "industry_exclude", "value": sorted(set(industry_excludes))})

    # 未支持的维度提示
    for kw in _UNSUPPORTED:
        if kw in text:
            missing_data.append(f"「{kw}」当前版本未接入对应数据，该维度已忽略（详见 README 数据边界）。")

    if not conditions:
        raise ParseError("未能从输入中识别出可执行条件。示例句式：\n"
                         "· 经营改善、估值合理、走势相对稳定\n"
                         "· 市盈率不超过30倍，剔除银行，不要ST\n"
                         "· 高股息且ROE大于15%，市值超过1000亿")

    conflicts = detect_conflicts(conditions, tags)
    return {
        "source": "rule",
        "raw": text,
        "conditions": conditions,
        "intent_tags": tags,
        "conflicts": conflicts,
        "clarifications": clarifications,
        "missing_data": missing_data,
        "summary": f"已解析 {len(conditions)} 个条件：" + "；".join(human_condition(c) for c in conditions),
        "note": llm_note or "当前使用规则解析器。配置 LLM_API_KEY / LLM_MODEL 后可解析更复杂的模糊表达。",
    }


# ---------------------------------------------------------------- LLM 解析

def _llm_system_prompt() -> str:
    metric_lines = []
    for mid, m in METRICS.items():
        direction = {True: "越大越好", False: "越小越好", None: "中性"}[m["higher_better"]]
        metric_lines.append(f"- {mid}（{m['label']}，单位{m['unit']}，{m['category']}，{direction}）：{m['desc']}")
    preset_lines = "；".join(f"{k}→{v['desc']}" for k, v in PRESET_INTENTS.items())
    return f"""你是 A 股选股意图解析器。把用户自然语言转成结构化筛选条件，只做理解，不做任何选股判断，不输出任何投资建议。

可用指标：
{chr(10).join(metric_lines)}

操作符：gt/ge（大于/大于等于）、lt/le（小于/小于等于）、between（区间 [lo,hi]）、pct_ge（全池前 100-x 分位）、pct_le（全池后 x 分位）。
特殊条件：{{"type":"exclude_st"}} 剔除ST；{{"type":"industry_exclude","value":["银行"]}} 排除行业（行业取值限：{'、'.join(INDUSTRIES)}）。

预设意图（用户说"经营改善""估值合理"等模糊词时按下述默认口径展开，并把默认口径写入 clarifications）：
{preset_lines}

输出要求：只输出一个 JSON 对象，禁止任何其他文字。结构：
{{
  "conditions": [ {{"metric":"pe_ttm","op":"le","value":40}}, {{"metric":"pe_ttm","op":"between","value":[0,40]}}, {{"type":"exclude_st"}}, {{"type":"industry_exclude","value":["银行"]}} ],
  "intent_tags": ["经营改善"],
  "clarifications": ["「估值合理」已按默认口径：PE∈[0,40]且PB∈[0,5] 解释"],
  "missing_data": ["「机构持仓」当前无数据，已忽略"]
}}
规则：
- 数值单位：百分比类指标直接用数字（20 表示 20%）；市值单位亿元；回撤为负值（如 -25 表示回撤25%）。
- 只使用上面给出的指标与操作符，禁止编造。
- 无法确定的口径必须写入 clarifications；出现不支持的维度写入 missing_data。
- 同一指标出现矛盾表达（如 既要PE<30 又要PE>50）时，按用户更强调的那个保留，并在 clarifications 中说明。"""


def _llm_parse(text: str) -> dict:
    import llm_client as lc
    parsed = lc.chat_json(_llm_system_prompt(), f"用户输入：{text}\n请输出 JSON。")
    conditions = parsed.get("conditions")
    if not isinstance(conditions, list):
        raise ParseError("LLM 输出缺少 conditions 字段。")
    conditions = validate_conditions(conditions)  # 非法条件抛错 → 触发回退
    tags = [t for t in (parsed.get("intent_tags") or []) if t in PRESET_INTENTS]
    clarifications = [str(c) for c in (parsed.get("clarifications") or [])]
    missing_data = [str(m) for m in (parsed.get("missing_data") or [])]
    conflicts = detect_conflicts(conditions, tags)
    return {
        "source": "llm",
        "raw": text,
        "conditions": conditions,
        "intent_tags": tags,
        "conflicts": conflicts,
        "clarifications": clarifications,
        "missing_data": missing_data,
        "summary": f"已解析 {len(conditions)} 个条件：" + "；".join(human_condition(c) for c in conditions),
        "note": "本次解析由 LLM 完成。",
    }


# ---------------------------------------------------------------- 统一入口

def parse(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ParseError("请输入选股意图，例如：经营改善、估值合理、走势相对稳定。")
    if llm_client.is_configured():
        try:
            return _llm_parse(text)
        except ParseError as e:
            # 结构/校验错误：回退规则解析并说明
            return _rule_parse(text, llm_note=f"LLM 解析未通过校验（{e}），已回退规则解析。")
        except llm_client.LlmError as e:
            return _rule_parse(text, llm_note=f"LLM 调用失败（{e}），已回退规则解析。")
    return _rule_parse(text)
