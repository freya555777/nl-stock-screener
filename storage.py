# -*- coding: utf-8 -*-
"""
策略存储（本地 JSON）
====================
保存用户筛选条件与关注列表。仅存策略本身，不存用户画像/持仓等隐私数据；
文件位于 ./data/saves.json，可随仓库提交（不含任何 Key）。
"""
import datetime
import json
import os
import uuid

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_SAVES_PATH = os.path.join(_DATA_DIR, "saves.json")
_MAX_SAVES = 50


def _load():
    try:
        with open(_SAVES_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("saves", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(saves):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SAVES_PATH, "w", encoding="utf-8") as f:
        json.dump({"saves": saves}, f, ensure_ascii=False, indent=2)


def list_saves():
    return _load()


def create_save(name, conditions, codes):
    name = (name or "").strip()
    if not name:
        raise ValueError("请为策略命名。")
    if len(name) > 50:
        raise ValueError("策略名称最长 50 个字符。")
    saves = _load()
    if len(saves) >= _MAX_SAVES:
        raise ValueError(f"最多保存 {_MAX_SAVES} 个策略，请先删除部分旧策略。")
    item = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "conditions": conditions,
        "codes": codes[:50],
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    saves.insert(0, item)
    _save(saves)
    return item


def delete_save(save_id):
    saves = _load()
    rest = [s for s in saves if s["id"] != save_id]
    if len(rest) == len(saves):
        raise ValueError("未找到该策略。")
    _save(rest)
    return {"deleted": save_id}
