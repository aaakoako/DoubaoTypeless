"""安全诊断快照：展示/导出运行状态，但不包含 API Key 或用户正文。"""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp

from config import Config
from paths import app_root
from providers_registry import detect_provider_name


_TEXT_FIELD_RE = re.compile(r"\b(text|before|after)='[^']*'", re.IGNORECASE)
_JSON_SECRET_RE = re.compile(
    r'("(?:api_key|llm_api_key|learn_api_key|authorization)"\s*:\s*")[^"]*(")',
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"\b(?:sk|ak|pk)-[A-Za-z0-9_\-]{8,}\b")


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def tcp_connects(host: str, port: int, timeout: float = 0.35) -> bool:
    """本机 TCP 可连接性探测；失败不抛异常。"""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def file_stat(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False, "size": 0, "modified": ""}
    try:
        st = p.stat()
        return {
            "path": str(p),
            "exists": True,
            "size": int(st.st_size),
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        }
    except OSError as e:
        return {"path": str(p), "exists": True, "error": str(e)}


def redact_log_line(line: str) -> str:
    """移除日志中可能出现的正文/API Key，只保留可诊断的结构信息。"""
    s = (line or "").rstrip("\n\r")
    s = _TEXT_FIELD_RE.sub(lambda m: f"{m.group(1)}='<redacted>'", s)
    s = _JSON_SECRET_RE.sub(r"\1<redacted>\2", s)
    s = _TOKEN_RE.sub("<redacted-token>", s)
    s = re.sub(r"(正文预览:\s*)'.*'", r"\1'<redacted>'", s)
    s = re.sub(r"(Authorization:\s*Bearer\s+)\S+", r"\1<redacted>", s, flags=re.IGNORECASE)
    return s[:700]


def safe_recent_log_lines(path: str | Path, max_lines: int = 80) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    interesting = [
        x
        for x in lines[-400:]
        if any(
            tag in x
            for tag in (
                "[bridge]",
                "[bridge.",
                "[suggest.",
                "[learn",
                "[probe.",
                "[update",
                "[hotkey]",
                "[插入结果]",
                "[自学习]",
            )
        )
    ]
    return [redact_log_line(x) for x in interesting[-max_lines:]]


def config_summary(config: Config) -> dict[str, Any]:
    """只返回结构状态；不返回任何 Key 或正文。"""
    return {
        "bridge_port": config.bridge_port,
        "clipboard_protection": bool(config.clipboard_protection),
        "start_with_windows": bool(config.start_with_windows),
        "hotkeys_configured": {
            "toggle_review": bool((config.hotkey_toggle_review or "").strip()),
            "insert": bool((config.hotkey_insert or "").strip()),
        },
        "suggest": {
            "enabled": bool(config.llm_enabled),
            "provider": detect_provider_name(config.llm_base_url),
            "base_url_configured": bool((config.llm_base_url or "").strip()),
            "api_key_configured": bool((config.llm_api_key or "").strip()),
            "model": (config.llm_model or "").strip(),
            "timeout": config.llm_timeout,
        },
        "learn": {
            "enabled": bool(config.learn_enabled),
            "provider": detect_provider_name(config.learn_base_url or config.llm_base_url),
            "base_url_configured": bool((config.learn_base_url or "").strip()),
            "api_key_configured": bool((config.learn_api_key or "").strip()),
            "model": (config.learn_model or "").strip(),
            "timeout": config.learn_timeout,
            "batch_interval": int(config.learn_batch_interval or 0),
            "learn_when_no_diff": bool(config.learn_when_no_diff),
        },
        "paths": {
            "dictionary": file_stat(config.dictionary_path),
            "domain_terms": file_stat(config.domain_terms_path),
            "review_history": file_stat(config.review_history_path),
            "learn_pending": file_stat(config.learn_pending_path),
            "dict_pending": file_stat(config.dict_suggestions_pending_path),
        },
        "dict_write_mode": config.dict_write_mode,
        "dict_conflict_policy": config.dict_conflict_policy,
    }


def build_diagnostics_snapshot(
    config: Config,
    *,
    runtime: dict[str, Any] | None = None,
    app_version: str = "",
    model_health: dict[str, Any] | None = None,
    include_log_tail: bool = True,
) -> dict[str, Any]:
    rt = runtime or {}
    bridge = dict(rt.get("bridge") or {})
    configured_port = int(bridge.get("configured_port") or config.bridge_port)
    runtime_port = int(bridge.get("runtime_port") or configured_port)
    local_ip = _local_ip()
    log_path = app_root() / "debug.log"
    out: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "app": {
            "version": (app_version or "").strip(),
            "root": str(app_root()),
            "frozen": bool(getattr(sys, "frozen", False)),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "network": {
            "local_ip": local_ip,
            "configured_port": configured_port,
            "runtime_port": runtime_port,
            "localhost_tcp_ok": tcp_connects("127.0.0.1", runtime_port),
        },
        "bridge": bridge,
        "runtime": {
            "loop_running": bool(rt.get("loop_running")),
            "redact_user_logs": bool(rt.get("redact_user_logs")),
            "learn_pending_count": int(rt.get("learn_pending_count") or 0),
            "pending_raw_len": int(rt.get("pending_raw_len") or 0),
            "tray_state": str(rt.get("tray_state") or ""),
        },
        "model_health": model_health or {},
        "config": config_summary(config),
        "files": {
            "debug_log": file_stat(log_path),
            "config_json": file_stat(app_root() / "config.json"),
        },
        "environment": {
            "DT_VERBOSE_LOG": bool(os.environ.get("DT_VERBOSE_LOG")),
            "DT_GITHUB_MIRROR": bool(os.environ.get("DT_GITHUB_MIRROR")),
            "DT_SKIP_AUTO_UPDATE_CHECK": bool(os.environ.get("DT_SKIP_AUTO_UPDATE_CHECK")),
        },
    }
    if include_log_tail:
        out["recent_log"] = safe_recent_log_lines(log_path)
    return out


def export_diagnostics_json(snapshot: dict[str, Any], directory: str | Path | None = None) -> Path:
    dest_dir = Path(directory) if directory is not None else app_root()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = dest_dir / f"doubao_diagnostics_{stamp}.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def run_connection_self_check(
    *,
    port: int,
    connected_clients: int = 0,
    last_stable_at: str = "",
    timeout: float = 1.2,
) -> dict[str, Any]:
    """检查本机桥接链路；只访问 127.0.0.1，不包含用户正文。"""
    started = time.perf_counter()
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})

    local_ip = _local_ip()
    if local_ip == "127.0.0.1":
        add("本机 IP", "warn", "仅检测到 127.0.0.1；若手机连不上，检查 WiFi/防火墙/网卡。")
    else:
        add("本机 IP", "ok", f"检测到局域网地址 {local_ip}")

    if not tcp_connects("127.0.0.1", port, timeout=timeout):
        add("端口监听", "fail", f"127.0.0.1:{port} 不可连接；桥接服务未启动或端口被拦截。")
        return {
            "overall": "fail",
            "summary": "桥接端口不可连接",
            "checks": checks,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    add("端口监听", "ok", f"127.0.0.1:{port} 可连接")

    http_ok = False
    ws_ok = False
    http_url = f"http://127.0.0.1:{port}/"
    ws_url = f"ws://127.0.0.1:{port}/ws"
    client_timeout = aiohttp.ClientTimeout(total=max(timeout, 0.5))
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(http_url) as resp:
                body = await resp.text()
                http_ok = resp.status == 200 and "DoubaoTypeless" in body and "{{WS_URL}}" not in body
                if http_ok:
                    add("手机页面", "ok", "本机可打开手机页面，页面模板已正确渲染。")
                else:
                    add("手机页面", "fail", f"HTTP {resp.status}，页面内容异常。")
            if http_ok:
                async with session.ws_connect(ws_url) as ws:
                    await ws.send_json({"type": "ping"})
                    msg = await ws.receive(timeout=max(timeout, 0.5))
                    ws_ok = msg.type == aiohttp.WSMsgType.TEXT and '"pong"' in (msg.data or "")
                    if ws_ok:
                        add("WebSocket", "ok", "WebSocket 可连接，ping/pong 正常。")
                    else:
                        add("WebSocket", "fail", f"WebSocket 已连接但未收到 pong（type={msg.type}）。")
    except Exception as e:
        label = "WebSocket" if http_ok else "手机页面"
        add(label, "fail", f"{type(e).__name__}: {e}")

    if connected_clients > 0:
        add("手机在线", "ok", f"当前已有 {connected_clients} 台手机连接。")
    else:
        add("手机在线", "warn", "当前没有手机保持连接；请在手机浏览器打开设置页里的地址。")

    if last_stable_at:
        add("稳定稿", "ok", f"最近一次稳定稿时间：{last_stable_at}")
    else:
        add("稳定稿", "warn", "尚未收到 stable/send；手机输入后等待自动同步或点「立即发送」。")

    statuses = [c["status"] for c in checks]
    overall = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "ok")
    summary = {
        "ok": "桥接链路正常",
        "warn": "桥接可用，但仍有待确认项",
        "fail": "桥接链路存在阻断",
    }[overall]
    if not ws_ok and overall != "fail":
        overall = "fail"
        summary = "WebSocket 自检失败"
    return {
        "overall": overall,
        "summary": summary,
        "checks": checks,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
