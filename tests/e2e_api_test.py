# -*- coding: utf-8 -*-
"""
端到端 API 测试（需先启动服务：python app.py）
=============================================
覆盖：meta → parse → screen → whatif → compare → backtest → saves CRUD → quotes/refresh
运行：python tests/e2e_api_test.py [base_url]
"""
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name} {detail}")


def call(path, body=None, method=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"},
        method=method or ("GET" if data is None else "POST"),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 业务错误同样返回 ApiResponse 信封，这里读回 body
        return json.loads(e.read().decode("utf-8"))


print("== meta ==")
meta = call("/api/meta")
check("meta 返回指标", len(meta["data"]["metrics"]) >= 20, f"{len(meta['data']['metrics'])} 个指标")
check("meta 返回示例句", len(meta["data"]["examples"]) >= 4)
check("meta 返回数据状态", "mode" in meta["data"]["data_status"])

print("== parse ==")
p = call("/api/parse", {"text": "经营改善、估值合理、走势相对稳定"})
conds = p["data"]["conditions"]
check("parse 成功", p["code"] == 0 and len(conds) >= 6, f"{len(conds)} 个条件")
check("parse 带意图标签", len(p["data"]["intent_tags"]) >= 3)
check("parse 带口径说明", len(p["data"]["clarifications"]) >= 3)

print("== screen ==")
s = call("/api/screen", {"conditions": conds, "limit": 30})
check("screen 成功", s["code"] == 0)
check("screen 返回入选", len(s["data"]["included"]) > 0, f"included={len(s['data']['included'])}")
check("screen 入选带解释", all(len(x["checks"]) == len(conds) for x in s["data"]["included"]))
check("screen 带被排除解释", len(s["data"]["excluded_near_miss"]) > 0)
check("screen 带数据口径", s["data"]["data_note"] != "")
codes = [x["code"] for x in s["data"]["included"]][:5]

print("== whatif ==")
w = call("/api/whatif", {"conditions": conds, "metric": "pe_ttm", "value": [0, 60]})
check("whatif 成功", w["code"] == 0)
check("whatif 数量守恒", w["data"]["before_count"] + w["data"]["added_count"] - w["data"]["removed_count"] == w["data"]["after_count"])

print("== compare ==")
c = call("/api/compare", {"codes": codes, "conditions": conds})
check("compare 成功", c["code"] == 0 and len(c["data"]["rows"]) == len(codes))

print("== backtest ==")
b = call("/api/backtest", {"codes": codes, "days": 20})
check("backtest 成功", b["code"] == 0)
check("backtest 序列长度", len(b["data"]["portfolio_series"]) == 21)
check("backtest 显式标注模拟", "模拟" in b["data"]["note"])

print("== saves CRUD ==")
sv = call("/api/saves", {"name": "E2E测试策略", "conditions": conds, "codes": codes})
check("save 创建", sv["code"] == 0 and sv["data"]["id"])
sv_id = sv["data"]["id"]
lst = call("/api/saves")
check("save 列表含新项", any(x["id"] == sv_id for x in lst["data"]["saves"]))
# 非法保存（空名）
bad = call("/api/saves", {"name": "", "conditions": conds, "codes": codes})
check("save 空名被拒", bad["code"] == 400)
dl = call("/api/saves/" + sv_id, None, "DELETE")
check("save 删除", dl["code"] == 0)

print("== quotes/refresh（真实网络，可能跳过）==")
try:
    q = call("/api/quotes/refresh", {})
    check("quotes/refresh 成功", q["code"] == 0 and q["data"]["applied_count"] > 0,
          f"applied={q['data']['applied_count']}")
except Exception as e:
    print("  跳过（网络不可用）:", e)

print("== 首页 ==")
with urllib.request.urlopen(BASE + "/", timeout=10) as resp:
    html = resp.read().decode("utf-8")
check("首页返回 HTML", "选股意图解释器" in html)

print()
print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    for f in FAIL:
        print(" -", f)
    sys.exit(1)
print("全部通过 ✓")
