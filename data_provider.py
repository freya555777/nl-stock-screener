# -*- coding: utf-8 -*-
"""
数据层（Data Layer）
====================
职责边界（对应题目要求"明确 AI、确定性筛选引擎和金融数据工具之间的职责边界"）：
- 数据层只负责"取数 + 标注来源/时点/口径"，不做任何筛选与判断；
- 筛选引擎只消费结构化指标，不关心数据来自演示库还是扶摇；
- AI 解析层只负责把自然语言转成结构化条件，不做筛选。

当前实现：
- DemoProvider：内置演示数据集（见 demo_data.py），无 Key 即可运行完整主链路；
- FuyaoProvider：扶摇 REST 适配器骨架，配置 FUYAO_API_KEY 后启用（接口契约见 README）；
- LiveQuoteRefresher：腾讯公开行情（qt.gtimg.cn）实时快照，用于覆盖 PE/PB/市值/换手率等
  行情类字段，财务类字段仍为演示口径；覆盖字段会携带 source 标注。
"""
import json
import os
import time
import urllib.parse
import urllib.request

import demo_data
from schema import DEMO_AS_OF, QUOTE_SOURCE_LABEL


class DataError(Exception):
    """数据获取失败（网络/鉴权/接口错误）。"""


class DemoProvider:
    name = "demo"
    label = "演示数据集"

    def get_universe(self):
        return [dict(s) for s in demo_data.UNIVERSE]

    def status(self):
        return {
            "mode": "demo",
            "label": self.label,
            "as_of_financials": DEMO_AS_OF,
            "note": "当前为演示数据：财务指标为构造数据，仅用于功能演示；行情字段可经实时行情刷新覆盖。",
        }


class FuyaoProvider:
    """扶摇 REST 适配器（骨架）。

    扶摇文档：https://fuyao.aicubes.cn/docs/
    接口形态：/api/<标的宇宙>/<数据类型>/<动作>，统一 ApiResponse 信封
             {code, message, request_id, data}；snake_case 字段、毫秒级 Unix 时间戳。
    启用方式：设置环境变量 FUYAO_API_KEY（可选 FUYAO_BASE_URL）。
    说明：笔试环境中未提供 Key，本适配器保持骨架形态；接入时按 README「数据接入」一节
    补齐字段映射（A股快照/财务报表 → 本产品指标）。能力以实际可调用工具为准。
    """

    name = "fuyao"
    label = "扶摇金融数据 API"

    def __init__(self):
        self.api_key = os.environ.get("FUYAO_API_KEY", "").strip()
        self.base_url = os.environ.get("FUYAO_BASE_URL", "https://fuyao.aicubes.cn").rstrip("/")

    def _request(self, path: str):
        if not self.api_key:
            raise DataError("未配置 FUYAO_API_KEY，扶摇数据不可用。请设置环境变量后重试。")
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # 网络/超时/解析错误统一抛 DataError
            raise DataError(f"扶摇接口调用失败: {e}")
        if payload.get("code") not in (0, "0", None):
            raise DataError(f"扶摇接口返回业务错误: {payload.get('message', payload)}")
        return payload.get("data")

    def get_universe(self):
        """TODO(接入时按扶摇文档实现)：
        1. 标的列表：/api/A股/标的列表/... → 基础信息（代码/名称/行业/ST）
        2. 行情快照：/api/A股/行情快照/... → pe_ttm/pb/mkt_cap/turnover/amount/mom/vol
        3. 财务报表：/api/A股/财务报表/... → revenue_yoy/profit_yoy/roe/gross_margin/...
        返回结构与 demo_data.UNIVERSE 一致（STOCK_KEYS），缺失字段置 None 并标注。
        """
        if not self.api_key:
            raise DataError("未配置 FUYAO_API_KEY，扶摇数据不可用。请设置环境变量后重试。")
        raise DataError("扶摇适配器为骨架实现：请在 README「数据接入」指引下补齐字段映射后使用。")


def get_provider():
    """按环境变量选择数据提供者；默认演示数据（保证开箱可跑）。"""
    if os.environ.get("FUYAO_API_KEY"):
        return FuyaoProvider()
    return DemoProvider()


# ---------------------------------------------------------------- 实时行情
# 腾讯公开行情接口（无需 Key），字段下标见 _parse_quote。仅作为演示增强：
# 若不可达则整体降级为纯演示数据，不影响主链路。
_TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q={codes}"


def _code_to_symbol(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    return "sz" + code


def _parse_quote(line: str):
    """解析 qt.gtimg.cn 单条行情。字段见公开约定：现价/涨跌幅/PE(TTM)/PB/总市值/换手率等。"""
    try:
        body = line.split('="', 1)[1].rstrip('"')
        f = body.split("~")
        if len(f) < 50:
            return None
        def num(i):
            try:
                v = float(f[i])
                return v
            except (ValueError, IndexError):
                return None
        return {
            "price": num(3),
            "pct_chg": num(31),
            "turnover": num(38),      # 换手率（单日，%）
            "pe_ttm": num(39),        # PE(TTM)
            "pb": num(46),            # PB
            "mkt_cap": num(45),       # 总市值（亿元）
            "ts": f[30] if len(f) > 30 else None,
        }
    except Exception:
        return None


def fetch_live_quotes(codes, batch=50, timeout=8):
    """批量拉取实时行情。返回 {code: {字段: 值}}，失败字段自动跳过；整体失败抛 DataError。"""
    result = {}
    symbols = [_code_to_symbol(c) for c in codes]
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        url = _TENCENT_QUOTE_URL.format(codes=",".join(chunk))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("gbk", errors="ignore")
        except Exception as e:
            raise DataError(f"实时行情接口不可达: {e}")
        for line in text.split(";"):
            if "=" not in line:
                continue
            sym = line.split("=", 1)[0].replace("v_", "").strip()
            q = _parse_quote(line)
            if q is None:
                continue
            # 反查原代码
            code = next((c for c in codes if _code_to_symbol(c) == sym), None)
            if code:
                result[code] = q
    if not result:
        raise DataError("实时行情解析失败：未获取到任何有效行情。")
    return result


def apply_live_quotes(universe, quotes, fetched_at):
    """把实时行情合并进股票池；被覆盖字段添加 source 标注。返回 (universe, applied_count)。"""
    applied = 0
    field_map = {
        "pe_ttm": "pe_ttm",
        "pb": "pb",
        "mkt_cap": "mkt_cap",
        "turnover": "turnover_20d",
    }
    for stock in universe:
        q = quotes.get(stock["code"])
        if not q:
            continue
        for qk, mk in field_map.items():
            v = q.get(qk)
            if v is not None:
                stock[mk] = v
                stock.setdefault("_sources", {})[mk] = {
                    "source": QUOTE_SOURCE_LABEL,
                    "ts": q.get("ts") or fetched_at,
                }
        applied += 1
    universe.sort(key=lambda s: s.get("_sources", {}) and 0 or 1)  # 有实时行情的排前面（演示友好）
    return universe, applied
