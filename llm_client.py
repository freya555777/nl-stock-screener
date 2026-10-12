# -*- coding: utf-8 -*-
"""
LLM 客户端（OpenAI 兼容，默认火山方舟）
======================================
仅负责"把自然语言 → 结构化 JSON"这一件事；不参与筛选与判断。
未配置 Key/模型 或 调用失败时，由 parser.py 自动回退到规则解析，保证主链路可用。
"""
import json
import os
import re
import urllib.request

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


class LlmError(Exception):
    """LLM 调用/解析失败（message 面向用户）。"""


def is_configured():
    return bool(os.environ.get("LLM_API_KEY")) and bool(os.environ.get("LLM_MODEL"))


def chat_json(system: str, user: str, temperature: float = 0.0, timeout: int = 25):
    """调用 chat/completions 并解析 JSON 输出。失败抛 LlmError。"""
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip()
    base = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    if not api_key or not model:
        raise LlmError("未配置 LLM_API_KEY / LLM_MODEL，无法调用 LLM。")
    body = json.dumps({
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise LlmError(f"LLM 调用失败: {e}")
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LlmError(f"LLM 返回结构异常: {e}")
    return _extract_json(content)


def _extract_json(text: str):
    """从模型输出中提取 JSON（容忍代码块包裹与前后杂讯）。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LlmError("LLM 输出中未找到 JSON。")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise LlmError(f"LLM 输出 JSON 解析失败: {e}")
