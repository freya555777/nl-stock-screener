# -*- coding: utf-8 -*-
"""
Flask 后端入口
==============
API 约定：统一响应信封 {code, message, data}（与扶摇 ApiResponse 风格一致）。
code=0 表示成功；业务/参数错误 code=400；数据源错误 code=502；未知错误 code=500。
启动：python app.py  →  http://127.0.0.1:8000
环境变量：
  FUYAO_API_KEY / FUYAO_BASE_URL   接入扶摇真实财务数据（可选，默认演示数据）
  LLM_API_KEY / LLM_MODEL / LLM_BASE_URL  接入 LLM 解析（可选，默认规则解析）
"""
import datetime
import os
import sys

from flask import Flask, jsonify, request, send_from_directory

import backtest
import data_provider
import engine
import parser
import storage
from demo_data import INDUSTRIES
from schema import METRICS, OPS, PRESET_INTENTS, SPECIAL_CONDITIONS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# 运行时数据状态（进程内存 + 可选缓存）
_provider = data_provider.get_provider()
_universe = _provider.get_universe()
_quotes_state = {"applied_at": None, "applied_count": 0, "mode": "demo"}

EXAMPLES = [
    "经营改善、估值合理、走势相对稳定",
    "市盈率不超过30倍，剔除银行和地产，不要ST",
    "高股息且ROE大于15%，市值超过1000亿，近60日涨幅超过10%",
    "低估值、高成长，排除白酒行业",
]


def _ok(data=None, message="ok"):
    return jsonify({"code": 0, "message": message, "data": data})


def _err(code, message):
    return jsonify({"code": code, "message": message, "data": None}), code


# ---------------------------------------------------------------- 页面
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ---------------------------------------------------------------- 元信息
@app.route("/api/meta")
def api_meta():
    return _ok({
        "metrics": {mid: {**m, "id": mid} for mid, m in METRICS.items()},
        "ops": OPS,
        "presets": {k: {"desc": v["desc"], "conditions": v["conditions"]} for k, v in PRESET_INTENTS.items()},
        "specials": SPECIAL_CONDITIONS,
        "industries": INDUSTRIES,
        "examples": EXAMPLES,
        "table_metrics": engine.TABLE_METRICS,
        "data_status": _provider.status(),
        "quote_state": _quotes_state,
        "llm_configured": parser.llm_client.is_configured(),
    })


# ---------------------------------------------------------------- NL 解析
@app.route("/api/parse", methods=["POST"])
def api_parse():
    body = request.get_json(silent=True) or {}
    try:
        result = parser.parse(body.get("text", ""))
        return _ok(result)
    except parser.ParseError as e:
        return _err(400, str(e))


# ---------------------------------------------------------------- 筛选
@app.route("/api/screen", methods=["POST"])
def api_screen():
    body = request.get_json(silent=True) or {}
    try:
        conditions = engine.validate_conditions(body.get("conditions"))
        limit = min(int(body.get("limit", 30)), 100)
        result = engine.screen(conditions, universe=_universe, limit=limit)
        return _ok(result)
    except engine.ConditionError as e:
        return _err(400, str(e))
    except (TypeError, ValueError) as e:
        return _err(400, f"参数非法: {e}")


# ---------------------------------------------------------------- 敏感性
@app.route("/api/whatif", methods=["POST"])
def api_whatif():
    body = request.get_json(silent=True) or {}
    try:
        result = engine.whatif(
            body.get("conditions"), body.get("metric"), body.get("value"),
            universe=_universe,
        )
        return _ok(result)
    except engine.ConditionError as e:
        return _err(400, str(e))
    except (TypeError, ValueError) as e:
        return _err(400, f"参数非法: {e}")


# ---------------------------------------------------------------- 比较
@app.route("/api/compare", methods=["POST"])
def api_compare():
    body = request.get_json(silent=True) or {}
    codes = body.get("codes") or []
    if not isinstance(codes, list) or not codes:
        return _err(400, "请至少选择一只股票进行比较。")
    conditions = None
    if body.get("conditions"):
        try:
            conditions = engine.validate_conditions(body.get("conditions"))
        except engine.ConditionError as e:
            return _err(400, str(e))
    return _ok(engine.compare(codes, universe=_universe, conditions=conditions))


# ---------------------------------------------------------------- 回测
@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    body = request.get_json(silent=True) or {}
    codes = body.get("codes") or []
    days = body.get("days", 20)
    if not isinstance(codes, list) or not codes:
        return _err(400, "请至少选择一只股票进行回测。")
    try:
        return _ok(backtest.run_backtest(codes, days=days, universe=_universe))
    except ValueError as e:
        return _err(400, str(e))


# ---------------------------------------------------------------- 策略保存
@app.route("/api/saves", methods=["GET"])
def api_saves_list():
    return _ok({"saves": storage.list_saves()})


@app.route("/api/saves", methods=["POST"])
def api_saves_create():
    body = request.get_json(silent=True) or {}
    try:
        conditions = engine.validate_conditions(body.get("conditions"))
        item = storage.create_save(body.get("name"), conditions, body.get("codes") or [])
        return _ok(item)
    except (engine.ConditionError, ValueError) as e:
        return _err(400, str(e))


@app.route("/api/saves/<save_id>", methods=["DELETE"])
def api_saves_delete(save_id):
    try:
        return _ok(storage.delete_save(save_id))
    except ValueError as e:
        return _err(400, str(e))


# ---------------------------------------------------------------- 实时行情
@app.route("/api/quotes/refresh", methods=["POST"])
def api_quotes_refresh():
    codes = [s["code"] for s in _universe]
    try:
        quotes = data_provider.fetch_live_quotes(codes)
        merged, applied = data_provider.apply_live_quotes(_universe, quotes,
                                                          datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        _quotes_state.update({
            "applied_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "applied_count": applied,
            "mode": "mixed" if applied else "demo",
        })
        return _ok({"applied_count": applied, "total": len(codes), "state": dict(_quotes_state)})
    except data_provider.DataError as e:
        return _err(502, f"{e}（已保持演示数据，不影响筛选主链路）")


# ---------------------------------------------------------------- 健康检查
@app.route("/api/health")
def api_health():
    return _ok({
        "status": "ok",
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "universe_size": len(_universe),
        "data_mode": _provider.name,
        "llm_configured": parser.llm_client.is_configured(),
    })


@app.errorhandler(404)
def _not_found(e):
    return _err(404, "接口不存在")


@app.errorhandler(Exception)
def _internal(e):
    app.logger.exception("未处理异常")
    return _err(500, f"服务内部错误: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"* 选股意图解释器已启动: http://127.0.0.1:{port}")
    print(f"* 数据模式: {_provider.label} | LLM: {'已配置' if parser.llm_client.is_configured() else '规则解析'}")
    app.run(host="0.0.0.0", port=port, debug=False)
