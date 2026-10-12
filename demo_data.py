# -*- coding: utf-8 -*-
"""
演示数据集（Demo Universe）
==========================
重要声明：
- 本数据集用于在**没有扶摇/iFinD Key 的情况下**演示产品主链路，所有财务与行情指标
  均为**构造的演示数据**（数值量级参照公开常识，但非实时、非真实财务数据）。
- 前端会全局展示「演示数据」横幅；接入扶摇 API 后切换为真实数据（见 fuyao_client.py）。
- 缺失值用 None 表示，产品必须显式展示"数据缺失"，不得静默补 0 或跳过。

数据结构：每只股票一个 dict，字段见 STOCK_KEYS。
"""
import random

from schema import DEMO_AS_OF

# 风险类别（用于补齐次要指标的取值区间，仅影响演示数据）
# cons=稳健（银行/电力/白酒/煤炭/公用） mid=中性（消费/医药/家电/机械） gro=成长（半导体/新能源/计算机/算力）
_CLASS_PARAMS = {
    "cons": {"vol": (12, 22), "dd": (-6, -18), "to": (0.2, 1.0), "amt": (3, 20), "ps": (2, 8)},
    "mid":  {"vol": (20, 35), "dd": (-10, -25), "to": (0.5, 1.8), "amt": (3, 25), "ps": (2, 12)},
    "gro":  {"vol": (28, 60), "dd": (-15, -40), "to": (1.0, 3.5), "amt": (4, 60), "ps": (5, 30)},
}

# 金融类行业：无毛利率/净利率/资产负债率口径
_FIN_INDUSTRIES = {"银行", "保险", "券商"}

# (code, name, sector, industry, risk_class, hot_rank, overrides)
# overrides 中的键：pe_ttm pb dividend_yield mkt_cap revenue_yoy profit_yoy roe gross_margin
#                 vol_20d drawdown_60d turnover_20d amount_20d mom_60d 等；未给出的由 _fill 补齐
_STOCK_SPECS = [
    # ---- 消费：白酒 ----
    ("600519", "贵州茅台", "消费", "白酒", "cons", 1,
     {"pe_ttm": 19.8, "pb": 6.4, "dividend_yield": 3.4, "mkt_cap": 16101, "revenue_yoy": 15, "profit_yoy": 12,
      "roe": 30, "gross_margin": 91, "mom_60d": 8, "amount_20d": 42}),
    ("000858", "五粮液", "消费", "白酒", "cons", 12,
     {"pe_ttm": 16, "pb": 3.6, "dividend_yield": 3.8, "mkt_cap": 6200, "revenue_yoy": 12, "profit_yoy": 10,
      "roe": 24, "gross_margin": 77, "mom_60d": 6, "amount_20d": 28}),
    ("600809", "山西汾酒", "消费", "白酒", "cons", 30,
     {"pe_ttm": 25, "pb": 8, "dividend_yield": 1.8, "mkt_cap": 2600, "revenue_yoy": 18, "profit_yoy": 20,
      "roe": 28, "gross_margin": 76, "vol_20d": 30, "drawdown_60d": -20, "mom_60d": 15, "amount_20d": 22}),
    ("000568", "泸州老窖", "消费", "白酒", "cons", 22,
     {"pe_ttm": 15, "pb": 4.6, "dividend_yield": 4.0, "mkt_cap": 2300, "revenue_yoy": 14, "profit_yoy": 13,
      "roe": 28, "gross_margin": 88, "vol_20d": 26, "drawdown_60d": -16, "mom_60d": 10, "amount_20d": 20}),
    ("002304", "洋河股份", "消费", "白酒", "cons", 60,
     {"pe_ttm": 12, "pb": 2.5, "dividend_yield": 5.2, "mkt_cap": 1500, "revenue_yoy": 3, "profit_yoy": -2,
      "roe": 18, "gross_margin": 74, "mom_60d": -5, "amount_20d": 10}),
    # ---- 消费：食品 ----
    ("600887", "伊利股份", "消费", "食品饮料", "cons", 45,
     {"pe_ttm": 15, "pb": 3.0, "dividend_yield": 4.2, "mkt_cap": 1700, "revenue_yoy": 6, "profit_yoy": 7,
      "roe": 20, "gross_margin": 33, "mom_60d": 5, "amount_20d": 12}),
    ("603288", "海天味业", "消费", "食品饮料", "cons", 70,
     {"pe_ttm": 35, "pb": 8.0, "dividend_yield": 1.6, "mkt_cap": 1900, "revenue_yoy": 8, "profit_yoy": 6,
      "roe": 22, "gross_margin": 36, "mom_60d": 2, "amount_20d": 9}),
    ("002311", "海大集团", "消费", "农林牧渔", "mid", 150,
     {"pe_ttm": 20, "pb": 4.0, "dividend_yield": 1.2, "mkt_cap": 900, "revenue_yoy": 10, "profit_yoy": 20,
      "roe": 18, "gross_margin": 12, "mom_60d": 12, "amount_20d": 8}),
    # ---- 金融：银行 ----
    ("600036", "招商银行", "金融", "银行", "cons", 15,
     {"pe_ttm": 6.5, "pb": 0.95, "dividend_yield": 5.6, "mkt_cap": 9000, "revenue_yoy": 2, "profit_yoy": 5,
      "roe": 15, "gross_margin": None, "mom_60d": 6, "amount_20d": 18}),
    ("601166", "兴业银行", "金融", "银行", "cons", 55,
     {"pe_ttm": 5.0, "pb": 0.55, "dividend_yield": 5.8, "mkt_cap": 3900, "revenue_yoy": 1, "profit_yoy": 4,
      "roe": 11, "gross_margin": None, "mom_60d": 3, "amount_20d": 12}),
    ("601398", "工商银行", "金融", "银行", "cons", 40,
     {"pe_ttm": 5.5, "pb": 0.58, "dividend_yield": 5.6, "mkt_cap": 21000, "revenue_yoy": 1, "profit_yoy": 4,
      "roe": 10.5, "gross_margin": None, "mom_60d": 4, "amount_20d": 16}),
    ("601288", "农业银行", "金融", "银行", "cons", 52,
     {"pe_ttm": 5.2, "pb": 0.60, "dividend_yield": 5.4, "mkt_cap": 17000, "revenue_yoy": 1, "profit_yoy": 4,
      "roe": 10, "gross_margin": None, "mom_60d": 5, "amount_20d": 14}),
    # ---- 金融：保险/券商 ----
    ("601318", "中国平安", "金融", "保险", "cons", 20,
     {"pe_ttm": 8, "pb": 0.9, "dividend_yield": 5.2, "mkt_cap": 7800, "revenue_yoy": 2, "profit_yoy": 8,
      "roe": 13, "gross_margin": None, "mom_60d": 8, "amount_20d": 22}),
    ("601628", "中国人寿", "金融", "保险", "cons", 80,
     {"pe_ttm": 12, "pb": 1.5, "dividend_yield": 2.6, "mkt_cap": 4200, "revenue_yoy": 3, "profit_yoy": 10,
      "roe": 10, "gross_margin": None, "mom_60d": 10, "amount_20d": 10}),
    ("600030", "中信证券", "金融", "券商", "cons", 35,
     {"pe_ttm": 15, "pb": 1.2, "dividend_yield": 2.8, "mkt_cap": 3200, "revenue_yoy": 5, "profit_yoy": 7,
      "roe": 8, "gross_margin": None, "mom_60d": 12, "amount_20d": 25}),
    ("300059", "东方财富", "金融", "券商", "gro", 18,
     {"pe_ttm": 25, "pb": 3.5, "dividend_yield": 0.8, "mkt_cap": 2500, "revenue_yoy": 10, "profit_yoy": 12,
      "roe": 13, "gross_margin": None, "vol_20d": 32, "drawdown_60d": -20, "mom_60d": 18, "amount_20d": 45}),
    # ---- 能源：煤炭/电力 ----
    ("601088", "中国神华", "能源", "煤炭", "cons", 28,
     {"pe_ttm": 9, "pb": 1.4, "dividend_yield": 7.2, "mkt_cap": 7500, "revenue_yoy": 3, "profit_yoy": 6,
      "roe": 16, "gross_margin": 32, "mom_60d": 5, "amount_20d": 12}),
    ("601225", "陕西煤业", "能源", "煤炭", "cons", 66,
     {"pe_ttm": 8, "pb": 1.6, "dividend_yield": 6.5, "mkt_cap": 2300, "revenue_yoy": 2, "profit_yoy": 5,
      "roe": 18, "gross_margin": 40, "mom_60d": 4, "amount_20d": 8}),
    ("600900", "长江电力", "能源", "电力", "cons", 32,
     {"pe_ttm": 18, "pb": 2.8, "dividend_yield": 3.6, "mkt_cap": 7100, "revenue_yoy": 4, "profit_yoy": 6,
      "roe": 15, "gross_margin": 60, "vol_20d": 11, "drawdown_60d": -5, "mom_60d": 3, "amount_20d": 10}),
    ("601985", "中国核电", "能源", "电力", "cons", 90,
     {"pe_ttm": 15, "pb": 2.2, "dividend_yield": 2.5, "mkt_cap": 1900, "revenue_yoy": 6, "profit_yoy": 8,
      "roe": 12, "gross_margin": 48, "mom_60d": 7, "amount_20d": 6}),
    # ---- 新能源 ----
    ("300750", "宁德时代", "新能源", "电池", "gro", 2,
     {"pe_ttm": 22, "pb": 4.8, "dividend_yield": 1.5, "mkt_cap": 11500, "revenue_yoy": 20, "profit_yoy": 30,
      "roe": 22, "gross_margin": 25, "vol_20d": 35, "drawdown_60d": -22, "mom_60d": 20, "amount_20d": 60}),
    ("002594", "比亚迪", "新能源", "汽车", "gro", 4,
     {"pe_ttm": 25, "pb": 5.5, "dividend_yield": 0.9, "mkt_cap": 9000, "revenue_yoy": 25, "profit_yoy": 32,
      "roe": 22, "gross_margin": 20, "vol_20d": 34, "drawdown_60d": -21, "mom_60d": 18, "amount_20d": 55}),
    ("601012", "隆基绿能", "新能源", "光伏", "gro", 48,
     {"pe_ttm": 40, "pb": 2.1, "dividend_yield": 1.0, "mkt_cap": 1400, "revenue_yoy": -5, "profit_yoy": -30,
      "roe": 4, "gross_margin": 15, "vol_20d": 42, "drawdown_60d": -30, "mom_60d": -12, "amount_20d": 20}),
    ("600438", "通威股份", "新能源", "光伏", "gro", 58,
     {"pe_ttm": 30, "pb": 2.0, "dividend_yield": 1.2, "mkt_cap": 1200, "revenue_yoy": -8, "profit_yoy": -20,
      "roe": 6, "gross_margin": 18, "vol_20d": 40, "drawdown_60d": -28, "mom_60d": -10, "amount_20d": 15}),
    ("300274", "阳光电源", "新能源", "光伏", "gro", 26,
     {"pe_ttm": 18, "pb": 4.5, "dividend_yield": 1.1, "mkt_cap": 1500, "revenue_yoy": 25, "profit_yoy": 30,
      "roe": 25, "gross_margin": 28, "vol_20d": 38, "drawdown_60d": -24, "mom_60d": 22, "amount_20d": 18}),
    # ---- 锂 ----
    ("002460", "赣锋锂业", "新能源", "锂矿", "gro", 38,
     {"pe_ttm": 25, "pb": 2.5, "dividend_yield": 0.5, "mkt_cap": 900, "revenue_yoy": 20, "profit_yoy": 40,
      "roe": 10, "gross_margin": 22, "vol_20d": 45, "drawdown_60d": -32, "mom_60d": 25, "amount_20d": 14}),
    ("002466", "天齐锂业", "新能源", "锂矿", "gro", 62,
     {"pe_ttm": None, "pb": 1.8, "dividend_yield": 0.4, "mkt_cap": 800, "revenue_yoy": 10, "profit_yoy": None,
      "roe": -3, "gross_margin": 30, "vol_20d": 50, "drawdown_60d": -35, "mom_60d": 15, "amount_20d": 10}),
    ("603799", "华友钴业", "新能源", "锂矿", "gro", 75,
     {"pe_ttm": 20, "pb": 3.0, "dividend_yield": 0.8, "mkt_cap": 700, "revenue_yoy": 15, "profit_yoy": 30,
      "roe": 15, "gross_margin": 16, "vol_20d": 42, "drawdown_60d": -28, "mom_60d": 20, "amount_20d": 12}),
    # ---- 半导体 ----
    ("688981", "中芯国际", "科技", "半导体", "gro", 9,
     {"pe_ttm": 60, "pb": 3.2, "dividend_yield": 0.2, "mkt_cap": 4800, "revenue_yoy": 12, "profit_yoy": 10,
      "roe": 6, "gross_margin": 22, "vol_20d": 40, "drawdown_60d": -25, "mom_60d": 15, "amount_20d": 35}),
    ("002371", "北方华创", "科技", "半导体", "gro", 16,
     {"pe_ttm": 35, "pb": 6.0, "dividend_yield": 0.3, "mkt_cap": 1800, "revenue_yoy": 25, "profit_yoy": 40,
      "roe": 18, "gross_margin": 40, "vol_20d": 38, "drawdown_60d": -23, "mom_60d": 25, "amount_20d": 20}),
    ("603501", "韦尔股份", "科技", "半导体", "gro", 33,
     {"pe_ttm": 45, "pb": 5.0, "dividend_yield": 0.2, "mkt_cap": 1300, "revenue_yoy": 20, "profit_yoy": 35,
      "roe": 12, "gross_margin": 32, "vol_20d": 42, "drawdown_60d": -27, "mom_60d": 22, "amount_20d": 16}),
    ("603986", "兆易创新", "科技", "半导体", "gro", 44,
     {"pe_ttm": 40, "pb": 4.5, "dividend_yield": 0.3, "mkt_cap": 900, "revenue_yoy": 22, "profit_yoy": 30,
      "roe": 13, "gross_margin": 38, "vol_20d": 44, "drawdown_60d": -28, "mom_60d": 20, "amount_20d": 12}),
    ("688008", "澜起科技", "科技", "半导体", "gro", 27,
     {"pe_ttm": 50, "pb": 6.0, "dividend_yield": 0.2, "mkt_cap": 800, "revenue_yoy": 30, "profit_yoy": 40,
      "roe": 15, "gross_margin": 55, "vol_20d": 45, "drawdown_60d": -29, "mom_60d": 30, "amount_20d": 10}),
    ("688256", "寒武纪", "科技", "半导体", "gro", 8,
     {"pe_ttm": None, "pb": 12, "dividend_yield": 0, "mkt_cap": 1400, "revenue_yoy": 40, "profit_yoy": None,
      "roe": -5, "gross_margin": 60, "vol_20d": 60, "drawdown_60d": -40, "mom_60d": 35, "amount_20d": 25}),
    ("688041", "海光信息", "科技", "半导体", "gro", 10,
     {"pe_ttm": 70, "pb": 8, "dividend_yield": 0, "mkt_cap": 2000, "revenue_yoy": 35, "profit_yoy": 45,
      "roe": 8, "gross_margin": 62, "vol_20d": 50, "drawdown_60d": -33, "mom_60d": 32, "amount_20d": 22}),
    # ---- 医药 ----
    ("600276", "恒瑞医药", "医药", "创新药", "mid", 21,
     {"pe_ttm": 45, "pb": 6.5, "dividend_yield": 0.4, "mkt_cap": 2600, "revenue_yoy": 10, "profit_yoy": 15,
      "roe": 14, "gross_margin": 85, "mom_60d": 12, "amount_20d": 18}),
    ("300760", "迈瑞医疗", "医药", "医疗器械", "mid", 41,
     {"pe_ttm": 28, "pb": 6.0, "dividend_yield": 1.8, "mkt_cap": 2900, "revenue_yoy": 12, "profit_yoy": 15,
      "roe": 26, "gross_margin": 64, "mom_60d": 8, "amount_20d": 10}),
    ("603259", "药明康德", "医药", "医疗服务", "mid", 68,
     {"pe_ttm": 20, "pb": 3.0, "dividend_yield": 1.2, "mkt_cap": 1400, "revenue_yoy": 5, "profit_yoy": 10,
      "roe": 15, "gross_margin": 41, "mom_60d": 6, "amount_20d": 12}),
    ("600436", "片仔癀", "医药", "中药", "mid", 85,
     {"pe_ttm": 45, "pb": 8.0, "dividend_yield": 1.0, "mkt_cap": 1200, "revenue_yoy": 12, "profit_yoy": 15,
      "roe": 20, "gross_margin": 45, "mom_60d": 10, "amount_20d": 5}),
    ("300015", "爱尔眼科", "医药", "医疗服务", "mid", 72,
     {"pe_ttm": 30, "pb": 7.0, "dividend_yield": 0.5, "mkt_cap": 1100, "revenue_yoy": 12, "profit_yoy": 15,
      "roe": 18, "gross_margin": 50, "vol_20d": 32, "drawdown_60d": -21, "mom_60d": 10, "amount_20d": 8}),
    ("688235", "百济神州", "医药", "创新药", "gro", 50,
     {"pe_ttm": None, "pb": 5.0, "dividend_yield": 0, "mkt_cap": 1800, "revenue_yoy": 25, "profit_yoy": None,
      "roe": None, "gross_margin": 85, "vol_20d": 40, "drawdown_60d": -26, "mom_60d": 8, "amount_20d": 12}),
    # ---- 家电 ----
    ("000333", "美的集团", "消费", "家电", "mid", 25,
     {"pe_ttm": 13, "pb": 2.6, "dividend_yield": 4.6, "mkt_cap": 5200, "revenue_yoy": 8, "profit_yoy": 12,
      "roe": 22, "gross_margin": 26, "mom_60d": 10, "amount_20d": 15}),
    ("000651", "格力电器", "消费", "家电", "mid", 42,
     {"pe_ttm": 8, "pb": 1.9, "dividend_yield": 6.2, "mkt_cap": 2200, "revenue_yoy": 3, "profit_yoy": 8,
      "roe": 21, "gross_margin": 28, "mom_60d": 5, "amount_20d": 10}),
    ("002415", "海康威视", "科技", "安防", "mid", 47,
     {"pe_ttm": 20, "pb": 3.6, "dividend_yield": 2.8, "mkt_cap": 2800, "revenue_yoy": 6, "profit_yoy": 8,
      "roe": 19, "gross_margin": 44, "mom_60d": 5, "amount_20d": 12}),
    ("002475", "立讯精密", "科技", "消费电子", "mid", 29,
     {"pe_ttm": 20, "pb": 4.0, "dividend_yield": 0.8, "mkt_cap": 2300, "revenue_yoy": 15, "profit_yoy": 22,
      "roe": 20, "gross_margin": 12, "vol_20d": 30, "drawdown_60d": -19, "mom_60d": 15, "amount_20d": 18}),
    ("002241", "歌尔股份", "科技", "消费电子", "mid", 64,
     {"pe_ttm": 25, "pb": 3.2, "dividend_yield": 0.6, "mkt_cap": 800, "revenue_yoy": 12, "profit_yoy": 30,
      "roe": 12, "gross_margin": 11, "vol_20d": 36, "drawdown_60d": -23, "mom_60d": 18, "amount_20d": 12}),
    # ---- 计算机/软件 ----
    ("002230", "科大讯飞", "科技", "人工智能", "gro", 31,
     {"pe_ttm": 80, "pb": 5.0, "dividend_yield": 0.2, "mkt_cap": 1100, "revenue_yoy": 8, "profit_yoy": -5,
      "roe": 5, "gross_margin": 40, "vol_20d": 38, "drawdown_60d": -25, "mom_60d": 10, "amount_20d": 14}),
    ("688111", "金山办公", "科技", "软件", "gro", 54,
     {"pe_ttm": 70, "pb": 9.0, "dividend_yield": 0.3, "mkt_cap": 1300, "revenue_yoy": 15, "profit_yoy": 18,
      "roe": 14, "gross_margin": 85, "vol_20d": 36, "drawdown_60d": -22, "mom_60d": 12, "amount_20d": 8}),
    ("600588", "用友网络", "科技", "软件", "mid", 110,
     {"pe_ttm": 60, "pb": 3.5, "dividend_yield": 0.4, "mkt_cap": 500, "revenue_yoy": 5, "profit_yoy": -10,
      "roe": 3, "gross_margin": 52, "vol_20d": 34, "drawdown_60d": -24, "mom_60d": -5, "amount_20d": 6}),
    ("600570", "恒生电子", "科技", "软件", "mid", 88,
     {"pe_ttm": 35, "pb": 6.0, "dividend_yield": 0.5, "mkt_cap": 600, "revenue_yoy": 8, "profit_yoy": 12,
      "roe": 17, "gross_margin": 78, "vol_20d": 32, "drawdown_60d": -20, "mom_60d": 10, "amount_20d": 7}),
    ("002410", "广联达", "科技", "软件", "mid", 130,
     {"pe_ttm": 30, "pb": 4.0, "dividend_yield": 0.6, "mkt_cap": 400, "revenue_yoy": 4, "profit_yoy": 5,
      "roe": 8, "gross_margin": 82, "vol_20d": 30, "drawdown_60d": -20, "mom_60d": -3, "amount_20d": 4}),
    # ---- 通信/算力 ----
    ("000063", "中兴通讯", "科技", "通信设备", "mid", 24,
     {"pe_ttm": 18, "pb": 2.5, "dividend_yield": 2.2, "mkt_cap": 1700, "revenue_yoy": 8, "profit_yoy": 12,
      "roe": 15, "gross_margin": 42, "mom_60d": 12, "amount_20d": 20}),
    ("300308", "中际旭创", "科技", "光模块", "gro", 5,
     {"pe_ttm": 30, "pb": 7.0, "dividend_yield": 0.3, "mkt_cap": 1200, "revenue_yoy": 40, "profit_yoy": 60,
      "roe": 20, "gross_margin": 34, "vol_20d": 48, "drawdown_60d": -30, "mom_60d": 40, "amount_20d": 30}),
    ("300502", "新易盛", "科技", "光模块", "gro", 11,
     {"pe_ttm": 35, "pb": 8.0, "dividend_yield": 0.2, "mkt_cap": 800, "revenue_yoy": 45, "profit_yoy": 65,
      "roe": 22, "gross_margin": 36, "vol_20d": 52, "drawdown_60d": -32, "mom_60d": 45, "amount_20d": 20}),
    # ---- 军工 ----
    ("600760", "中航沈飞", "军工", "航空装备", "mid", 76,
     {"pe_ttm": 40, "pb": 6.0, "dividend_yield": 0.5, "mkt_cap": 1300, "revenue_yoy": 10, "profit_yoy": 15,
      "roe": 12, "gross_margin": 10, "mom_60d": 10, "amount_20d": 8}),
    ("600150", "中国船舶", "军工", "船舶制造", "mid", 46,
     {"pe_ttm": 30, "pb": 3.0, "dividend_yield": 0.6, "mkt_cap": 1500, "revenue_yoy": 15, "profit_yoy": 50,
      "roe": 10, "gross_margin": 12, "mom_60d": 15, "amount_20d": 10}),
    # ---- 有色/材料 ----
    ("601899", "紫金矿业", "材料", "有色金属", "mid", 13,
     {"pe_ttm": 12, "pb": 3.0, "dividend_yield": 2.2, "mkt_cap": 4500, "revenue_yoy": 8, "profit_yoy": 25,
      "roe": 20, "gross_margin": 18, "mom_60d": 15, "amount_20d": 25}),
    ("600111", "北方稀土", "材料", "有色金属", "mid", 57,
     {"pe_ttm": 30, "pb": 4.0, "dividend_yield": 0.8, "mkt_cap": 1100, "revenue_yoy": 10, "profit_yoy": 15,
      "roe": 12, "gross_margin": 22, "vol_20d": 36, "drawdown_60d": -23, "mom_60d": 12, "amount_20d": 10}),
    ("601600", "中国铝业", "材料", "有色金属", "mid", 73,
     {"pe_ttm": 12, "pb": 2.0, "dividend_yield": 1.5, "mkt_cap": 1400, "revenue_yoy": 6, "profit_yoy": 25,
      "roe": 15, "gross_margin": 15, "mom_60d": 12, "amount_20d": 8}),
    ("603993", "洛阳钼业", "材料", "有色金属", "mid", 49,
     {"pe_ttm": 15, "pb": 2.8, "dividend_yield": 1.8, "mkt_cap": 1300, "revenue_yoy": 10, "profit_yoy": 30,
      "roe": 18, "gross_margin": 16, "mom_60d": 18, "amount_20d": 12}),
    ("600309", "万华化学", "材料", "化工", "mid", 51,
     {"pe_ttm": 14, "pb": 2.5, "dividend_yield": 2.5, "mkt_cap": 2400, "revenue_yoy": 6, "profit_yoy": 12,
      "roe": 18, "gross_margin": 17, "mom_60d": 8, "amount_20d": 12}),
    # ---- 机械/制造 ----
    ("600031", "三一重工", "制造", "工程机械", "mid", 43,
     {"pe_ttm": 20, "pb": 2.8, "dividend_yield": 1.8, "mkt_cap": 1600, "revenue_yoy": 10, "profit_yoy": 25,
      "roe": 15, "gross_margin": 28, "mom_60d": 12, "amount_20d": 10}),
    ("300124", "汇川技术", "制造", "工控自动化", "gro", 59,
     {"pe_ttm": 30, "pb": 6.0, "dividend_yield": 0.6, "mkt_cap": 1300, "revenue_yoy": 15, "profit_yoy": 20,
      "roe": 22, "gross_margin": 34, "mom_60d": 15, "amount_20d": 10}),
    ("002050", "三花智控", "制造", "汽车零部件", "mid", 95,
     {"pe_ttm": 25, "pb": 4.5, "dividend_yield": 1.0, "mkt_cap": 900, "revenue_yoy": 12, "profit_yoy": 18,
      "roe": 16, "gross_margin": 27, "mom_60d": 14, "amount_20d": 8}),
    # ---- 地产/建筑 ----
    ("000002", "万科A", "地产", "地产", "cons", 61,
     {"pe_ttm": 12, "pb": 0.7, "dividend_yield": 2.0, "mkt_cap": 900, "revenue_yoy": -10, "profit_yoy": -35,
      "roe": 6, "gross_margin": 16, "mom_60d": -8, "amount_20d": 10}),
    ("600048", "保利发展", "地产", "地产", "cons", 78,
     {"pe_ttm": 10, "pb": 0.6, "dividend_yield": 3.0, "mkt_cap": 1000, "revenue_yoy": -8, "profit_yoy": -25,
      "roe": 5, "gross_margin": 15, "mom_60d": -6, "amount_20d": 8}),
    ("601668", "中国建筑", "地产", "建筑", "cons", 83,
     {"pe_ttm": 5, "pb": 0.6, "dividend_yield": 4.6, "mkt_cap": 2500, "revenue_yoy": 4, "profit_yoy": 6,
      "roe": 11, "gross_margin": 10, "mom_60d": 3, "amount_20d": 8}),
    ("601390", "中国中铁", "地产", "建筑", "cons", 120,
     {"pe_ttm": 6, "pb": 0.7, "dividend_yield": 3.4, "mkt_cap": 1500, "revenue_yoy": 3, "profit_yoy": 5,
      "roe": 10, "gross_margin": 9, "mom_60d": 2, "amount_20d": 6}),
    # ---- 农业 ----
    ("300498", "温氏股份", "农业", "养殖", "mid", 92,
     {"pe_ttm": 15, "pb": 3.0, "dividend_yield": 1.5, "mkt_cap": 1000, "revenue_yoy": 8, "profit_yoy": 50,
      "roe": 14, "gross_margin": 13, "mom_60d": 15, "amount_20d": 6}),
    ("002714", "牧原股份", "农业", "养殖", "mid", 37,
     {"pe_ttm": 12, "pb": 3.5, "dividend_yield": 1.0, "mkt_cap": 1600, "revenue_yoy": 10, "profit_yoy": 45,
      "roe": 20, "gross_margin": 18, "mom_60d": 18, "amount_20d": 10}),
    # ---- 航运/物流 ----
    ("601919", "中远海控", "交运", "航运", "cons", 65,
     {"pe_ttm": 6, "pb": 1.2, "dividend_yield": 8.5, "mkt_cap": 2000, "revenue_yoy": 5, "profit_yoy": 8,
      "roe": 14, "gross_margin": 22, "mom_60d": 8, "amount_20d": 12}),
    ("002352", "顺丰控股", "交运", "快递", "mid", 71,
     {"pe_ttm": 22, "pb": 2.8, "dividend_yield": 1.2, "mkt_cap": 1900, "revenue_yoy": 8, "profit_yoy": 15,
      "roe": 12, "gross_margin": 14, "mom_60d": 8, "amount_20d": 9}),
    # ---- 面板 ----
    ("000725", "京东方A", "科技", "面板", "mid", 53,
     {"pe_ttm": 18, "pb": 1.2, "dividend_yield": 1.0, "mkt_cap": 1400, "revenue_yoy": 12, "profit_yoy": 30,
      "roe": 8, "gross_margin": 18, "mom_60d": 12, "amount_20d": 15}),
    ("000100", "TCL科技", "科技", "面板", "mid", 69,
     {"pe_ttm": 15, "pb": 1.5, "dividend_yield": 1.2, "mkt_cap": 900, "revenue_yoy": 10, "profit_yoy": 25,
      "roe": 9, "gross_margin": 16, "mom_60d": 10, "amount_20d": 12}),
    # ---- ST（演示口径标注，用于测试剔除ST条件） ----
    ("600734", "ST实达", "科技", "通信设备", "cons", 200,
     {"pe_ttm": None, "pb": 0.9, "dividend_yield": 0, "mkt_cap": 25, "revenue_yoy": -15, "profit_yoy": -60,
      "roe": -8, "gross_margin": 8, "mom_60d": -20, "amount_20d": 0.3}),
    ("000971", "ST高升", "科技", "软件", "cons", 210,
     {"pe_ttm": None, "pb": 1.1, "dividend_yield": 0, "mkt_cap": 18, "revenue_yoy": -20, "profit_yoy": -70,
      "roe": -10, "gross_margin": 12, "mom_60d": -25, "amount_20d": 0.2}),
]

STOCK_KEYS = [
    "code", "name", "sector", "industry", "is_st", "hot_rank",
    "pe_ttm", "pb", "ps_ttm", "dividend_yield", "mkt_cap",
    "revenue_yoy", "profit_yoy", "profit_cagr3",
    "gross_margin", "net_margin", "roe", "debt_ratio", "ocf_to_profit",
    "mom_20d", "mom_60d", "vol_20d", "drawdown_60d",
    "turnover_20d", "amount_20d",
]


def _fill_metrics(code: str, industry: str, risk: str, ov: dict) -> dict:
    """用确定性随机补齐次要指标（基于 code 种子），保证每次生成一致。"""
    rnd = random.Random(int(code) * 7919 % (2 ** 31))
    p = _CLASS_PARAMS[risk]
    m = {}

    def pick(rng_range):
        lo, hi = rng_range
        return round(rnd.uniform(lo, hi), 2)

    m["ps_ttm"] = ov.get("ps_ttm", round(pick(p["ps"]) * (1 if risk != "gro" else 1), 2))
    # 净利率 / 毛利率：金融类无此口径
    if industry in _FIN_INDUSTRIES:
        m["gross_margin"] = None
        m["net_margin"] = None
        m["debt_ratio"] = None
    else:
        m["net_margin"] = ov.get("net_margin", round(max(pick((2, 30)), -8), 2))
        if "debt_ratio" not in ov:
            m["debt_ratio"] = round(pick((58, 68)), 1) if industry in ("地产", "建筑") else round(pick((32, 60)), 1)
    m["ocf_to_profit"] = round(pick((0.7, 1.6)), 2)
    # 3年复合增速：以当期净利同比为锚
    prof = ov.get("profit_yoy")
    if prof is None:
        m["profit_cagr3"] = None
    else:
        m["profit_cagr3"] = round(max(prof * 0.65 + pick((-8, 8)), -40), 1)
    # 20日涨幅：与60日涨幅同向但更小
    mom60 = ov.get("mom_60d", 0)
    m["mom_20d"] = round(mom60 * 0.35 + pick((-6, 6)), 1)
    return m


def build_universe():
    """构建演示股票池：每只股票包含 STOCK_KEYS 全部字段 + data_mode 标记。"""
    stocks = []
    for (code, name, sector, industry, risk, hot, ov) in _STOCK_SPECS:
        fill = _fill_metrics(code, industry, risk, ov)
        merged = {
            "code": code,
            "name": name,
            "sector": sector,
            "industry": industry,
            "is_st": name.startswith("ST"),
            "hot_rank": hot,
        }
        for k in STOCK_KEYS:
            if k in ("code", "name", "sector", "industry", "is_st", "hot_rank"):
                continue
            merged[k] = ov.get(k, fill.get(k))
        merged["data_mode"] = "demo"
        merged["as_of"] = DEMO_AS_OF
        stocks.append(merged)
    return stocks


UNIVERSE = build_universe()
UNIVERSE_BY_CODE = {s["code"]: s for s in UNIVERSE}

# 行业列表（用于排除行业条件的候选）
INDUSTRIES = sorted({s["industry"] for s in UNIVERSE})

if __name__ == "__main__":
    print(f"演示股票池规模: {len(UNIVERSE)} 只")
    print(f"行业数量: {len(INDUSTRIES)}")
    missing = [(s["code"], s["name"]) for s in UNIVERSE if s["pe_ttm"] is None]
    print(f"PE 缺失的股票（用于测试数据缺失路径）: {missing}")
