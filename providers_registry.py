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
        "billing": "官方 API 按 Token 计费（deepseek-chat / reasoner）；与网页/App 体验版账户无关。",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "Claude (Anthropic)": {
        "url": "https://api.anthropic.com/v1",
        "temperature": 0.3,
        "billing": "Anthropic 控制台按量；原生为 Messages API。若走 OpenAI 兼容代理，请填代理 Base URL，勿与直连 Messages 混用。",
        "models": [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "claude-opus-4-5",
            "claude-sonnet-4-5",
            "claude-opus-4-1",
            "claude-sonnet-4-0",
            "claude-opus-4-0",
            "claude-3-5-sonnet-20241022",
        ],
    },
    "智谱 (GLM)": {
        "url": "https://open.bigmodel.cn/api/paas/v4",
        "temperature": 0.3,
        "billing": "开放平台线路（api/paas/v4）：扣账户余额/资源包按量，与「智谱 Coding Plan」订阅额度不是同一套，Base URL 与密钥场景勿混。",
        "models": [
            "glm-4-flash",
            "glm-4-flash-250414",
            "glm-4-air",
            "glm-4.7",
            "glm-5",
            "glm-5-turbo",
            "glm-5.1",
        ],
    },
    "智谱 Coding Plan (GLM)": {
        "url": "https://open.bigmodel.cn/api/coding/paas/v4",
        "temperature": 0.3,
        "billing": "GLM Coding Plan 等编码套餐线路（api/coding/paas/v4）。加 Key 时常要求 Authentication Key；与 paas 按量线路分开选。",
        "models": [
            "glm-5.1",
            "glm-5",
            "glm-5-turbo",
            "glm-4.7",
            "glm-4.6",
            "glm-4.5",
            "glm-4.5-air",
        ],
    },
    "MiniMax": {
        "url": "https://api.minimaxi.com/v1",
        "temperature": 0.3,
        "billing": "Token Plan：此 Base + Token Plan Key；与按量 Key 不互通。勿填 …/anthropic（Anthropic 协议）。国际选「MiniMax 国际」。",
        "models": [
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2.1-highspeed",
            "MiniMax-M2",
        ],
    },
    "MiniMax (国际 api.minimax.io)": {
        "url": "https://api.minimax.io/v1",
        "temperature": 0.3,
        "billing": "国际区域 OpenAI 兼容端点 api.minimax.io/v1；与 api.minimaxi.com 不同，密钥勿混用。",
        "models": [
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2.1-highspeed",
            "MiniMax-M2",
        ],
    },
    "Qwen (阿里云)": {
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "temperature": 0.3,
        "billing": "DashScope 兼容模式；按量/资源包以阿里云百炼控制台为准，编码类专享权益若分开展示请对照官方说明选 Key。",
        "models": ["qwen-turbo", "qwen-flash", "qwen-plus", "qwen-max", "qwen-long"],
    },
    "豆包 (火山引擎)": {
        "url": "https://ark.cn-beijing.volces.com/api/v3",
        "temperature": 0.3,
        "billing": "火山方舟推理接入点；Model 填 Endpoint ID，计费随方舟实例/后付费方案，在火山控制台单独查看。",
        "models": [],
    },
    "Moonshot (Kimi)": {
        "url": "https://api.moonshot.cn/v1",
        "temperature": 0.3,
        "billing": "Kimi 标准 API 多为同一 Base。若含 Kimi Code Plan / 编码类套餐，抵扣以 Moonshot 控制台为准，与智谱 Coding 规则不必相同。",
        "models": [
            "kimi-k2.5",
            "kimi-k2-0905-preview",
            "kimi-k2-0711-preview",
            "kimi-k2-turbo-preview",
            "kimi-k2-thinking-turbo",
            "kimi-k2-thinking",
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
            "moonshot-v1-auto",
            "moonshot-v1-8k-vision-preview",
            "moonshot-v1-32k-vision-preview",
            "moonshot-v1-128k-vision-preview",
        ],
    },
    "OpenAI": {
        "url": "https://api.openai.com/v1",
        "temperature": 0.3,
        "billing": "OpenAI 平台按量；Chat Completions 与 Responses API 计费项不同，本工具当前走 Chat 兼容路径。",
        "models": [
            "gpt-5.4",
            "gpt-5.4-pro",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "o4-mini",
        ],
    },
    "硅基流动 (SiliconFlow)": {
        "url": "https://api.siliconflow.cn/v1",
        "temperature": 0.3,
        "billing": "硅基流动统一按 Token 扣费；模型 id 多为「厂商/模型」形式，与各原厂直开账户分开充值。",
        "models": [
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
            "Qwen/Qwen2.5-7B-Instruct",
        ],
    },
    "OpenRouter": {
        "url": "https://openrouter.ai/api/v1",
        "temperature": 0.3,
        "billing": "OpenRouter 聚合计费，按所选模型价目从 OR 余额扣；与直连 OpenAI/Anthropic 账单无关。",
        "models": [
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-2.0-flash-001",
            "google/gemini-2.5-flash-preview-05-20",
            "meta-llama/llama-3.3-70b-instruct",
            "deepseek/deepseek-chat",
        ],
    },
    "Groq": {
        "url": "https://api.groq.com/openai/v1",
        "temperature": 0.3,
        "billing": "GroqCloud 免费档与付费方案均有速率/日限额，以控制台为准。",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3-32b",
            "meta-llama/llama-4-scout-17b-16e-instruct",
        ],
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
    providers["自定义"] = {
        "url": "",
        "models": [],
        "billing": "自选 OpenAI 兼容地址。同一厂商「编码/Coding 套餐」与「按量/OpenAPI」常为不同 Base URL，密钥与账单也常分离，勿混填。",
    }
    return providers


LLM_PROVIDERS: dict[str, dict] = load_llm_providers()


def provider_billing_hint(provider: str) -> str:
    """厂商预设中的计费/线路说明，供设置界面展示。"""
    info = LLM_PROVIDERS.get((provider or "").strip()) or {}
    return str(info.get("billing") or "").strip()


def detect_provider_name(url: str) -> str:
    """由 Base URL 推断设置里 Provider 下拉项名称（与旧 GUI 逻辑一致）。"""
    for name, info in LLM_PROVIDERS.items():
        preset_url = info.get("url", "")
        if preset_url and url and preset_url.rstrip("/") == url.rstrip("/"):
            return name
    return "自定义" if (url or "").strip() else "DeepSeek"
