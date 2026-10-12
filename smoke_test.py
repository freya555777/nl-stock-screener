# -*- coding: utf-8 -*-
"""
冒烟测试（可复跑）：覆盖题目要求的三类场景
==========================================
1. 主链路：NL 解析 → 条件校验 → 确定性筛选 → 解释（入选/排除/差距）→ 敏感性 → 比较 → 回测
2. 数据缺失 / 接口失败：缺失指标显式标注；实时行情不可达时优雅降级
3. 边界 / 合规：空输入、非法条件、互斥条件、无买卖建议输出、来源标注

运行：python tests/smoke_test.py   （无外部依赖，不要求网络）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest
import demo_data
import engine
import llm_client
import parser
from schema import METRICS

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name} {detail}")


# ---------------- 1. 主链路 ----------------
print("== 1. 主链路 ==")
# 1.1 题目示例句解析
r = parser.parse("经营改善、估值合理、走势相对稳定")
check("示例句解析出条件", len(r["conditions"]) >= 6, f"got {len(r['conditions'])}")
check("示例句识别意图标签", set(r["intent_tags"]) >= {"经营改善", "估值合理", "走势稳定"}, str(r["intent_tags"]))
check("解析结果带口径说明", len(r["clarifications"]) >= 3, str(r["clarifications"][:2]))
check("解析结果无冲突", len(r["conflicts"]) == 0, str(r["conflicts"]))

# 1.2 数值+特殊条件
r2 = parser.parse("市盈率不超过30倍，剔除银行和地产，不要ST")
conds = r2["conditions"]
check("解析 PE≤30", any(c.get("metric") == "pe_ttm" and c.get("op") == "le" and c["value"] == 30 for c in conds))
check("解析排除行业", any(c.get("type") == "industry_exclude" and "银行" in c["value"] and "地产" in c["value"] for c in conds))
check("解析剔除ST", any(c.get("type") == "exclude_st" for c in conds))

# 1.3 条件校验（非法指标/操作符/空）
try:
    engine.validate_conditions([{"metric": "not_exist", "op": "gt", "value": 1}])
    check("非法指标被拒绝", False)
except engine.ConditionError:
    check("非法指标被拒绝", True)
try:
    engine.validate_conditions([])
    check("空条件被拒绝", False)
except engine.ConditionError:
    check("空条件被拒绝", True)
try:
    engine.validate_conditions([{"metric": "pe_ttm", "op": "between", "value": [50, 20]}])
    check("上下限颠倒被拒绝", False)
except engine.ConditionError:
    check("上下限颠倒被拒绝", True)

# 1.4 确定性筛选 + 解释
conds = engine.validate_conditions(r["conditions"])
res = engine.screen(conds)
check("筛选返回入选", len(res["included"]) > 0, f"included={len(res['included'])}")
check("入选含逐条件核验", all(len(s["checks"]) == len(conds) for s in res["included"]))
check("入选带满足度", all(0 <= s["score"] <= 100 for s in res["included"]))
check("被排除解释存在", res["excluded_total"] > 0 and res["excluded_near_miss"], f"total={res['excluded_total']}")
check("结果带数据口径", bool(res["data_note"]) and bool(res["generated_at"]))

# 1.5 缺失数据处理：包含 PE 为 None 的股票（寒武纪/天齐/百济）
miss_stocks = [s["name"] for s in demo_data.UNIVERSE if s["pe_ttm"] is None]
check("演示池含缺失股票", len(miss_stocks) >= 3, str(miss_stocks))
check("缺失股票被单独归类", res["excluded_missing"] > 0, f"missing={res['excluded_missing']}")
# 缺 PE 的股票不会被静默判为通过
for s in demo_data.UNIVERSE:
    if s["pe_ttm"] is None:
        ev = engine.evaluate_condition({"metric": "pe_ttm", "op": "le", "value": 30}, s, {})
        check("缺失不静默通过", ev["passed"] is None and ev["missing"] is True, s["name"])
        break

# 1.6 互斥冲突识别
conf = engine.detect_conflicts([
    {"metric": "pe_ttm", "op": "le", "value": 30},
    {"metric": "pe_ttm", "op": "ge", "value": 50},
])
check("同指标互斥被识别", any(c["level"] == "error" for c in conf), str(conf))
conf2 = engine.detect_conflicts([], ["大盘蓝筹", "小盘股"])
check("语义冲突被识别", any(c["level"] == "error" for c in conf2), str(conf2))

# 1.7 敏感性（what-if）
wi = engine.whatif(conds, "pe_ttm", [0, 60])
check("敏感性返回数量变化", "before_count" in wi and "after_count" in wi and "added" in wi and "removed" in wi)
check("敏感性新增/掉出合计正确", wi["before_count"] + wi["added_count"] - wi["removed_count"] == wi["after_count"],
      f"{wi['before_count']}+{wi['added_count']}-{wi['removed_count']}={wi['after_count']}")

# 1.8 比较
cmp = engine.compare(["600519", "600036", "300750"], conditions=conds)
check("比较返回3行", len(cmp["rows"]) == 3, f"got {len(cmp['rows'])}")
check("比较行含指标与核验", all(r["metrics"] and len(r["checks"]) == len(conds) for r in cmp["rows"]))

# 1.9 回测
bt = backtest.run_backtest(["600519", "600036", "300750"], days=20)
check("回测返回组合与基准", len(bt["portfolio_series"]) == 21 and len(bt["benchmark_series"]) == 21)
check("回测逐股明细", len(bt["rows"]) == 3)
check("回测显式标注模拟", "模拟" in bt["note"])

# ---------------- 2. 数据缺失 / 接口失败 ----------------
print("== 2. 数据缺失 / 接口失败 ==")
# 2.1 实时行情失败降级（把端点指向不可达端口，确定性触发失败）
try:
    import data_provider
    orig_url = data_provider._TENCENT_QUOTE_URL
    data_provider._TENCENT_QUOTE_URL = "http://127.0.0.1:1/q={codes}"
    try:
        data_provider.fetch_live_quotes(["600519"], batch=1, timeout=2)
        check("行情失败抛 DataError", False)
    finally:
        data_provider._TENCENT_QUOTE_URL = orig_url
except data_provider.DataError:
    check("行情失败抛 DataError", True)
# 2.2 未配置扶摇 Key → 明确报错而非静默
try:
    p = data_provider.FuyaoProvider()
    p.api_key = ""
    p.get_universe()
    check("扶摇未配 Key 明确报错", False)
except data_provider.DataError as e:
    check("扶摇未配 Key 明确报错", "FUYAO_API_KEY" in str(e))
# 2.3 LLM 未配置 → 规则解析可用
check("未配 LLM 时规则解析可用", not llm_client.is_configured() and r["source"] == "rule")

# ---------------- 3. 边界 / 合规 ----------------
print("== 3. 边界 / 合规 ==")
# 3.1 空输入 / 纯符号
for bad in ["", "  ", "？？？", "啊哈哈哈"]:
    try:
        parser.parse(bad)
        check(f"非法输入被拒绝: {bad!r}", False)
    except parser.ParseError:
        check(f"非法输入被拒绝: {bad!r}", True)
# 3.2 无买卖建议 / 无预测：检查关键接口返回里不存在建议性字段
import json
sample = json.dumps(res, ensure_ascii=False)
for banned in ["买入", "卖出", "目标价", "推荐买入", "上涨空间"]:
    check(f"结果不含投资建议字段: {banned}", banned not in sample)
# 3.3 来源标注：演示数据/实时行情标注存在
check("schema 含来源标注常量", hasattr(__import__("schema"), "DEMO_SOURCE_LABEL") and hasattr(__import__("schema"), "QUOTE_SOURCE_LABEL"))
# 3.4 指标口径完整（每个指标有单位/类别/方向）
check("全部指标口径完整", all("unit" in m and "category" in m and "higher_better" in m for m in METRICS.values()))

print()
print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败项：")
    for f in FAIL:
        print(" -", f)
    sys.exit(1)
print("全部通过 ✓")
