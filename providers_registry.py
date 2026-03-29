"""LLM 厂商预设（与 providers.json 合并）；供 GUI、Config 迁移与 Provider 名推断共用。"""
from __future__ import annotations

import json
from pathlib import Path

from paths import resource_dir

_PROVIDERS_PATH = resource_dir() / "providers.json"

_DEFAULT_PROVIDERS: dict[str, dict] = {
    "DeepSeek": {
        "url": "https://api.deepseek.com/v1",
        "temperature": 0.3,
        "models": ["deepseek-chat"],
    },
    "Claude (Anthropic)": {
        "url": "https://api.anthropic.com/v1",
        "temperature": 0.3,
        "models": [
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
            "claude-opus-4-5",
            "claude-3-5-sonnet-20241022",
        ],
    },
    "智谱 (GLM)": {
        "url": "https://open.bigmodel.cn/api/paas/v4",
        "temperature": 0.3,
        "models": ["glm-4-flash", "glm-4-flash-250414", "glm-4-air", "glm-5", "glm-5-turbo"],
    },
    "MiniMax": {
        "url": "https://api.minimaxi.com/v1",
        "temperature": 0.3,
        "models": ["MiniMax-M2.7-highspeed", "MiniMax-M2.7", "MiniMax-M2"],
    },
    "Qwen (阿里云)": {
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "temperature": 0.3,
        "models": ["qwen-turbo", "qwen-flash", "qwen-plus"],
    },
    "豆包 (火山引擎)": {
        "url": "https://ark.cn-beijing.volces.com/api/v3",
        "temperature": 0.3,
        "models": [],
    },
    "Moonshot (Kimi)": {
        "url": "https://api.moonshot.cn/v1",
        "temperature": 0.3,
        "models": ["kimi-k2-turbo-preview", "moonshot-v1-8k"],
    },
    "OpenAI": {
        "url": "https://api.openai.com/v1",
        "temperature": 0.3,
        "models": ["gpt-4o-mini", "gpt-4o"],
    },
}


def load_llm_providers() -> dict[str, dict]:
    providers = {name: dict(info) for name, info in _DEFAULT_PROVIDERS.items()}
    if _PROVIDERS_PATH.exists():
        try:
            with open(_PROVIDERS_PATH, "r", encoding="utf-8") as f:
                user_providers = json.load(f)
            for name, info in user_providers.items():
                base = dict(providers.get(name, {}))
                if isinstance(info, dict):
                    base.update(info)
                providers[name] = base
        except Exception:
            pass
    else:
        try:
            with open(_PROVIDERS_PATH, "w", encoding="utf-8") as f:
                json.dump(_DEFAULT_PROVIDERS, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    providers["自定义"] = {"url": "", "models": []}
    return providers


LLM_PROVIDERS: dict[str, dict] = load_llm_providers()


def detect_provider_name(url: str) -> str:
    """由 Base URL 推断设置里 Provider 下拉项名称（与旧 GUI 逻辑一致）。"""
    for name, info in LLM_PROVIDERS.items():
        preset_url = info.get("url", "")
        if preset_url and url and preset_url.rstrip("/") == url.rstrip("/"):
            return name
    return "自定义" if (url or "").strip() else "DeepSeek"
