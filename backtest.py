# -*- coding: utf-8 -*-
"""
演示回测（Demo Backtest）
========================
重要声明：本模块生成的价格序列为**模拟数据**（基于演示指标中的波动率/动量确定性构造），
仅用于演示"筛选结果 → 回测"的完整产品流程，不构成任何投资建议，也不代表真实历史表现。
真实回测应接入扶摇历史 K 线（fuyao_client 预留）。
"""
import datetime
import math
import random

import demo_data

_SERIES_DAYS = 60
_BENCH_PARAMS = {"vol": 0.18, "drift": 0.06}  # 沪深300 模拟参数（年化）


def _trading_dates(days):
    """从今天向前生成 days 个交易日日期（跳过周末，演示口径）。"""
    out = []
    d = datetime.date.today()
    while len(out) < days:
        if d.weekday() < 5:
            out.append(d)
        d -= datetime.timedelta(days=1)
    return list(reversed(out))


def _demo_series(stock, days=_SERIES_DAYS):
    """确定性模拟价格序列（60 个交易日），总收益锚定演示 mom_60d。"""
    seed = int(stock["code"]) * 100003
    rnd = random.Random(seed)
    vol = (stock.get("vol_20d") or 25.0) / 100.0
    mom60 = stock.get("mom_60d")
    total_ret = (mom60 if mom60 is not None else rnd.uniform(-10, 10)) / 100.0
    sigma_day = vol / math.sqrt(252)
    n = days - 1
    # 先产生随机游走，再整体锚定到 total_ret
    steps = [rnd.gauss(0, sigma_day) for _ in range(n)]
    drift = total_ret / n - (sum(steps) / n)
    prices = [100.0]
    for s in steps:
        prices.append(prices[-1] * (1 + drift + s))
    # 归一化末端收益 = total_ret
    scale = (1 + total_ret) / prices[-1]
    return [p * scale for p in prices]


def _bench_series(days=_SERIES_DAYS):
    rnd = random.Random(20261012)
    sigma_day = _BENCH_PARAMS["vol"] / math.sqrt(252)
    drift_day = _BENCH_PARAMS["drift"] / 252
    prices = [100.0]
    for _ in range(days - 1):
        prices.append(prices[-1] * (1 + drift_day + rnd.gauss(0, sigma_day)))
    return prices


def run_backtest(codes, days=20, universe=None):
    """等权买入持有 days 个交易日（演示）。返回回测结果与绘图序列。"""
    universe = universe or demo_data.UNIVERSE
    by_code = {s["code"]: s for s in universe}
    if not codes:
        raise ValueError("回测至少需要 1 只股票。")
    days = max(2, min(int(days), _SERIES_DAYS - 1))
    dates = _trading_dates(days + 1)

    rows, pf_series, bench_series = [], [], []
    rets = []
    for code in codes:
        s = by_code.get(code)
        if not s:
            continue
        series = _demo_series(s)
        p0 = series[-1 - days]
        p1 = series[-1]
        ret = (p1 / p0 - 1) * 100
        rets.append(ret)
        # 组合/基准序列都按日收益叠加（从窗口起点归一为 100）
        pf_series.append([100.0])
        for i in range(1, days + 1):
            pf_series[-1].append(pf_series[-1][-1] * (series[-1 - days + i] / series[-1 - days + i - 1]))
        rows.append({
            "code": code,
            "name": s["name"],
            "industry": s["industry"],
            "ret_pct": round(ret, 2),
            "vol_pct": s.get("vol_20d"),
            "simulated": True,
        })
    if not rows:
        raise ValueError("回测股票代码均不在当前股票池中。")

    n = len(rows)
    avg = sum(p[i] for p in pf_series) / n if n else [100.0]
    # 等权组合（逐日均值）
    pf = [round(sum(p[i] for p in pf_series) / n, 2) for i in range(days + 1)]
    b = _bench_series(days + 1)
    scale_b = 100.0 / b[0]
    bench = [round(x * scale_b, 2) for x in b]

    return {
        "days": days,
        "portfolio_ret_pct": round(sum(rets) / n, 2),
        "benchmark_ret_pct": round((bench[-1] / 100.0 - 1) * 100, 2),
        "excess_pct": round(sum(rets) / n - (bench[-1] / 100.0 - 1) * 100, 2),
        "stock_count": n,
        "rows": rows,
        "dates": [d.strftime("%m-%d") for d in dates],
        "portfolio_series": pf,
        "benchmark_series": bench,
        "note": "演示回测：价格为模拟序列（锚定演示动量/波动率），仅演示流程，不构成投资建议。",
    }
