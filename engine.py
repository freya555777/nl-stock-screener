# -*- coding: utf-8 -*-
"""
确定性筛选引擎（Deterministic Screening Engine）
=================================================
本模块是产品的事实层：不依赖任何 LLM，输入结构化条件，输出可解释的筛选结果。

职责：
1. 条件校验与归一化（拒绝非法指标/操作符/数值）
2. 冲突识别（同指标互斥区间、语义冲突）
3. 逐股逐条件求值：通过 / 未通过（含差距）/ 数据缺失
4. 入选排序（条件满足度）、被排除解释（决定性原因 + 差距）、接近入选（near-miss）
5. 条件敏感性（what-if）：修改一个条件，返回新增 / 掉出
6. 横向比较（compare）

口径约定：
- 百分比类指标 value 直接存百分数（20 表示 20%）；区间用 [lo, hi]
- 数据缺失（值为 None）→ 不判定为"未通过"，单独归类为"数据缺失"，并计入排除原因
- 相对差距 = (实际值 - 阈值) / |阈值|，用于排序与"还差多少"文案
"""
import datetime
from typing import Optional

import demo_data
from schema import (METRICS, OPS, SPECIAL_CONDITIONS, PRESET_INTENTS,
                    SEMANTIC_CONFLICTS, DEMO_SOURCE_LABEL, QUOTE_SOURCE_LABEL)

# 结果表格默认展示的关键指标
TABLE_METRICS = ["pe_ttm", "pb", "roe", "profit_yoy", "mkt_cap", "vol_20d", "dividend_yield", "mom_60d"]


class ConditionError(ValueError):
    """条件非法。"""


# ---------------------------------------------------------------- 条件校验

def validate_conditions(conditions) -> list:
    """校验并返回归一化条件列表；非法输入抛 ConditionError（message 面向用户）。"""
    if not isinstance(conditions, list) or len(conditions) == 0:
        raise ConditionError("请至少设置一个筛选条件。")
    out = []
    for i, c in enumerate(conditions):
        if not isinstance(c, dict):
            raise ConditionError(f"第 {i + 1} 个条件格式非法。")
        ctype = c.get("type", "metric")
        if ctype == "exclude_st":
            out.append({"type": "exclude_st"})
            continue
        if ctype == "industry_exclude":
            vals = c.get("value")
            if not isinstance(vals, list) or not vals:
                raise ConditionError("「排除行业」条件需要提供行业列表。")
            out.append({"type": "industry_exclude", "value": [str(v) for v in vals]})
            continue
        metric = c.get("metric")
        op = c.get("op")
        if metric not in METRICS:
            raise ConditionError(f"不支持的指标: {metric}（可用指标见 /api/meta）")
        if op not in OPS:
            raise ConditionError(f"不支持的比较符: {op}")
        value = c.get("value")
        nv = OPS[op]["n_values"]
        ok = False
        if nv == 1:
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        else:
            ok = (isinstance(value, list) and len(value) == 2
                  and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value))
        if not ok:
            raise ConditionError(f"「{METRICS[metric]['label']}」的 {OPS[op]['label']} 需要{'两个数值' if nv == 2 else '一个数值'}。")
        if op in ("pct_ge", "pct_le") and not (0 < value <= 100):
            raise ConditionError("分位条件取值须在 0~100 之间。")
        if op == "between" and value[0] > value[1]:
            raise ConditionError("区间条件：下限不能大于上限。")
        out.append({"metric": metric, "op": op, "value": value})
    return out


# ---------------------------------------------------------------- 冲突识别

def _interval(cond):
    """把数值条件转成区间，用于同指标互斥检测。"""
    m, op, v = cond["metric"], cond["op"], cond["value"]
    if op == "gt":
        return (v, float("inf")), False
    if op == "ge":
        return (v, float("inf")), True
    if op == "lt":
        return (float("-inf"), v), False
    if op == "le":
        return (float("-inf"), v), True
    if op == "between":
        return (v[0], v[1]), True
    return None  # pct 类单独处理


def _intervals_overlap(i1, i2):
    (a1, b1), c1 = i1
    (a2, b2), c2 = i2
    lo = max(a1, a2)
    hi = min(b1, b2)
    if lo > hi:
        return False
    if lo == hi:
        # 闭端点相交则成立
        return (c1 and a1 <= lo <= b1) or (c2 and a2 <= lo <= b2)
    return True


def detect_conflicts(conditions, intent_tags=None) -> list:
    """返回冲突列表 [{level: error|warning, message}]。"""
    conflicts = []
    metric_conds = [c for c in conditions if c.get("type", "metric") == "metric"]
    for i in range(len(metric_conds)):
        for j in range(i + 1, len(metric_conds)):
            a, b = metric_conds[i], metric_conds[j]
            if a["metric"] != b["metric"]:
                continue
            label = METRICS[a["metric"]]["label"]
            if a["op"] in ("pct_ge", "pct_le") or b["op"] in ("pct_ge", "pct_le"):
                if a["op"] in ("pct_ge", "pct_le") and b["op"] in ("pct_ge", "pct_le"):
                    # 分位互斥：pct_ge 90 与 pct_le 20 不可能同时满足
                    if (a["op"] == "pct_ge" and b["op"] == "pct_le" and a["value"] >= b["value"]) or \
                       (a["op"] == "pct_le" and b["op"] == "pct_ge" and b["value"] >= a["value"]):
                        conflicts.append({
                            "level": "error",
                            "message": f"「{label}」的分位条件互斥：要求同时处于前 {100 - a['value']}% 与后 {b['value']}%，无法同时满足。",
                        })
                continue
            ia, ib = _interval(a), _interval(b)
            if ia and ib and not _intervals_overlap(ia, ib):
                conflicts.append({
                    "level": "error",
                    "message": f"「{label}」设置了互斥区间：{human_condition(a)} 且 {human_condition(b)}，两者无法同时满足。",
                })
    # 语义冲突（基于意图标签）
    tags = set(intent_tags or [])
    for rule in SEMANTIC_CONFLICTS:
        pair = rule.get("match")
        if pair and pair[0] in tags and pair[1] in tags:
            conflicts.append({"level": rule["level"], "message": rule["msg"]})
    return conflicts


# ---------------------------------------------------------------- 文案

def human_condition(cond) -> str:
    """把条件转成用户可读文案。"""
    if cond.get("type") == "exclude_st":
        return "剔除 ST/*ST"
    if cond.get("type") == "industry_exclude":
        return "排除行业：" + "、".join(cond["value"])
    m, op, v = cond["metric"], cond["op"], cond["value"]
    label = METRICS[m]["label"]
    unit = METRICS[m]["unit"]
    if op == "between":
        return f"{label} ∈ [{v[0]}, {v[1]}] {unit}"
    if op == "pct_ge":
        return f"{label} 处于全池前 {100 - v}% 分位"
    if op == "pct_le":
        return f"{label} 处于全池后 {v}% 分位"
    olabel = OPS[op]["label"].replace("等于", "")
    return f"{label} {olabel} {v} {unit}"


def _fmt(v, unit="", nd=1):
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
        return f"{s}{unit}"
    return str(v)


def _rel_gap(actual, bound):
    if bound == 0:
        return actual - bound
    return (actual - bound) / abs(bound)


# ---------------------------------------------------------------- 单条件求值

def _percentile_rank(values, x):
    """x 在全池（非缺失）中的百分位 0~100。"""
    vals = sorted(values)
    if not vals:
        return 50.0
    import bisect
    idx = bisect.bisect_left(vals, x)
    return round(idx / len(vals) * 100, 1)


def evaluate_condition(cond, stock, universe_values) -> dict:
    """对单只股票求值单个条件。返回 {passed, value, missing, reason, gap}。
    passed: True/False；数据缺失时 passed=None, missing=True。"""
    if cond.get("type") == "exclude_st":
        return {"passed": not stock["is_st"], "value": None, "missing": False,
                "reason": "ST 标的被剔除（演示口径标注）" if stock["is_st"] else None, "gap": None}
    if cond.get("type") == "industry_exclude":
        excluded = stock["industry"] in cond["value"]
        return {"passed": not excluded, "value": stock["industry"], "missing": False,
                "reason": f"行业「{stock['industry']}」被排除" if excluded else None, "gap": None}

    metric, op, v = cond["metric"], cond["op"], cond["value"]
    actual = stock.get(metric)
    label = METRICS[metric]["label"]
    unit = METRICS[metric]["unit"]
    if actual is None:
        return {"passed": None, "value": None, "missing": True,
                "reason": f"「{label}」数据缺失（{DEMO_SOURCE_LABEL}中未提供该字段）", "gap": None}

    gap = None
    if op == "between":
        lo, hi = v
        if actual < lo or actual > hi:
            gap = min(actual - lo, actual - hi)
            passed = False
        else:
            gap = min(actual - lo, hi - actual)
            passed = True
    elif op in ("pct_ge", "pct_le"):
        pct = _percentile_rank(universe_values[metric], actual)
        gap = (pct - v) if op == "pct_ge" else (v - pct)
        passed = gap >= 0
    else:
        bound = v
        if op in ("gt", "ge"):
            gap = actual - bound
        else:  # lt / le
            gap = bound - actual
        passed = gap >= 0

    return {"passed": passed, "value": actual, "missing": False, "reason": None, "gap": gap}


# ---------------------------------------------------------------- 筛选主流程

def _universe_values(universe):
    """预计算各指标全池非缺失值（用于分位条件）。"""
    uv = {}
    for m in METRICS:
        uv[m] = [s[m] for s in universe if s.get(m) is not None]
    return uv


def screen(conditions, universe=None, limit=30, near_miss=5) -> dict:
    """执行筛选并生成解释。返回结构化结果（不含全池数据，控制载荷）。"""
    universe = universe or demo_data.UNIVERSE
    uv = _universe_values(universe)
    included, excluded = [], []
    for stock in universe:
        checks = []
        ok, has_missing, fail_reasons = True, False, []
        for cond in conditions:
            r = evaluate_condition(cond, stock, uv)
            checks.append({
                "condition": human_condition(cond),
                "metric": cond.get("metric"),
                "passed": r["passed"],
                "missing": r["missing"],
                "actual": r["value"],
                "actual_text": _fmt(r["value"], METRICS[cond["metric"]]["unit"] if cond.get("metric") else ""),
                "reason": r["reason"],
            })
            if r["missing"]:
                has_missing = True
                fail_reasons.append(r["reason"])
            elif r["passed"] is False:
                ok = False
                fail_reasons.append(r["reason"] or _fail_text(cond, stock, r))
        if ok and not has_missing:
            included.append(stock)
        else:
            excluded.append({"stock": stock, "checks": checks, "fail_reasons": fail_reasons,
                             "has_missing": has_missing})
    # 入选排序：条件满足度（相对差距归一化后取均值，0~1）
    def score_of(stock):
        gaps = []
        for cond in conditions:
            if cond.get("type", "metric") != "metric":
                continue
            r = evaluate_condition(cond, stock, uv)
            if r["gap"] is not None:
                gaps.append(max(0.0, min(1.0, abs(r["gap"]) if r["passed"] else 0.0)))
        return round(100 * (sum(gaps) / len(gaps) if gaps else 0), 1)

    included.sort(key=lambda s: (-score_of(s), s["hot_rank"]))
    included_out = [{
        "code": s["code"], "name": s["name"], "sector": s["sector"], "industry": s["industry"],
        "is_st": s["is_st"], "score": score_of(s),
        "metrics": {m: _fmt(s.get(m), METRICS[m]["unit"]) for m in TABLE_METRICS},
        "metrics_raw": {m: s.get(m) for m in TABLE_METRICS},
        "checks": [_check_view(cond, s, uv) for cond in conditions],
    } for s in included[:limit]]

    # 被排除：按最小相对差距排序取 near-miss
    def min_gap(stock):
        best = None
        for cond in conditions:
            if cond.get("type", "metric") != "metric":
                continue
            r = evaluate_condition(cond, stock, uv)
            if r["gap"] is not None:
                g = abs(r["gap"])
                best = g if best is None else min(best, g)
        return best if best is not None else float("inf")

    excluded.sort(key=lambda e: (e["has_missing"], min_gap(e["stock"])))
    excluded_out = [{
        "code": e["stock"]["code"], "name": e["stock"]["name"], "sector": e["stock"]["sector"],
        "industry": e["stock"]["industry"], "is_st": e["stock"]["is_st"],
        "has_missing": e["has_missing"],
        "fail_reasons": e["fail_reasons"][:3],
        "min_gap_text": _gap_text(e),
        "metrics": {m: _fmt(e["stock"].get(m), METRICS[m]["unit"]) for m in TABLE_METRICS},
        "checks": [_check_view(cond, e["stock"], uv) for cond in conditions],
    } for e in excluded[:near_miss]]

    missing_n = sum(1 for e in excluded if e["has_missing"])
    return {
        "universe_size": len(universe),
        "included": included_out,
        "excluded_near_miss": excluded_out,
        "excluded_total": len(excluded),
        "excluded_missing": missing_n,
        "conditions": [human_condition(c) for c in conditions],
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_note": "行情字段可含实时来源，财务指标为演示口径（详见字段级标注）",
    }


def _fail_text(cond, stock, r):
    m = cond["metric"]
    label = METRICS[m]["label"]
    unit = METRICS[m]["unit"]
    if cond["op"] == "between":
        lo, hi = cond["value"]
        if r["value"] < lo:
            return f"{label} 为 {_fmt(r['value'], unit)}，低于下限 {lo}{unit}"
        return f"{label} 为 {_fmt(r['value'], unit)}，高于上限 {hi}{unit}"
    if cond["op"] in ("pct_ge", "pct_le"):
        return f"{label} 分位不满足（实际分位 {_fmt(r['gap'] + cond['value'], '', 1)}%）"
    bound = cond["value"]
    olabel = OPS[cond["op"]]["label"].replace("等于", "")
    return f"{label} 为 {_fmt(r['value'], unit)}，未满足「{olabel} {bound}{unit}」"


def _gap_text(e):
    """被排除股票的差距文案：取第一个未通过且非缺失的条件原因。"""
    for c in e["checks"]:
        if c["passed"] is False and not c["missing"] and c["reason"]:
            return c["reason"]
    return "多项条件未满足"


def _check_view(cond, stock, uv):
    r = evaluate_condition(cond, stock, uv)
    return {
        "condition": human_condition(cond),
        "metric": cond.get("metric"),
        "passed": r["passed"],
        "missing": r["missing"],
        "actual_text": _fmt(r["value"], METRICS[cond["metric"]]["unit"] if cond.get("metric") else ""),
        "reason": r["reason"],
    }


# ---------------------------------------------------------------- 敏感性（What-if）

def whatif(conditions, metric_id, new_value, universe=None, limit=30, near_miss=3) -> dict:
    """修改一个条件后重跑，返回新增 / 掉出。"""
    conditions = validate_conditions(conditions)
    idx = next((i for i, c in enumerate(conditions)
                if c.get("metric") == metric_id and c.get("type", "metric") == "metric"), None)
    if idx is None:
        raise ConditionError("找不到要修改的条件，请先解析或添加该条件。")
    before_codes = {s["code"] for s in screen(conditions, universe, limit=10**6)["included"]}
    new_conds = [dict(c) for c in conditions]
    new_conds[idx]["value"] = new_value
    after = screen(new_conds, universe, limit=10**6)
    after_codes = {s["code"] for s in after["included"]}
    added = [s for s in after["included"] if s["code"] in after_codes - before_codes]
    removed_codes = before_codes - after_codes
    removed = [{"code": c, "name": next((s["name"] for s in universe if s["code"] == c), c)}
               for c in sorted(removed_codes)]
    return {
        "metric_label": METRICS[metric_id]["label"],
        "before_count": len(before_codes),
        "after_count": len(after_codes),
        "added": added[:limit],
        "removed": removed[:limit],
        "added_count": len(added),
        "removed_count": len(removed),
        "new_condition_text": human_condition(new_conds[idx]),
        "note": "敏感性分析仅反映当前条件集与当前数据快照下的确定性变化，不代表任何预测。",
    }


# ---------------------------------------------------------------- 比较

def compare(codes, universe=None, conditions=None) -> dict:
    universe = universe or demo_data.UNIVERSE
    by_code = {s["code"]: s for s in universe}
    uv = _universe_values(universe)
    rows = []
    for code in codes:
        s = by_code.get(code)
        if not s:
            continue
        checks = [_check_view(c, s, uv) for c in (conditions or [])]
        rows.append({
            "code": s["code"], "name": s["name"], "sector": s["sector"], "industry": s["industry"],
            "metrics": {m: _fmt(s.get(m), METRICS[m]["unit"]) for m in TABLE_METRICS},
            "checks": checks,
        })
    return {"rows": rows, "columns": TABLE_METRICS}
