"""Preview update check. Opens the public download page; never replaces daily-use or this preview."""
from __future__ import annotations

from typing import Any, Callable

try:
    from app_version import APP_VERSION, GITHUB_REPO_NAME, GITHUB_REPO_OWNER
except ImportError:
    APP_VERSION = "0.4.2"
    GITHUB_REPO_OWNER = "aaakoako"
    GITHUB_REPO_NAME = "DoubaoTypeless"

CHANNEL = "v3-preview"
DOWNLOAD_PAGE = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases"
API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"


def preview_version_label() -> str:
    from doubao_typeless.build_info import build_info
    info = build_info()
    label = {"v3-private-trial":"隔离体验版", "release-candidate":"发布候选", "stable":"正式版"}[info["channel"]]
    return f"DoubaoTypeless {info['version']} · {label} · {info['source_sha'][:8]}"


def check_preview_update(*, get_json: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    from doubao_typeless.build_info import build_info
    info = build_info()
    release = info['channel'] in {'stable', 'release-candidate'}
    current = info['version'] if release else APP_VERSION
    out: dict[str, Any] = {
        "channel": info['channel'] if release else CHANNEL,
        "current": current,
        "label": preview_version_label(),
        "page": DOWNLOAD_PAGE,
        "latest": "",
        "auto_replace": False,
        "writes_daily_use": False,
        "message": "这是隔离预览。只打开公开下载页，不会覆盖日用安装或本预览目录。",
        "update_available": False,
    }
    if release:
        out['message'] = '可查询正式版本；下载后运行安装程序升级，设置和草稿会保留。不会自动替换。'
    if get_json is None:
        return out
    try:
        body = get_json(API_LATEST) or {}
        if not isinstance(body, dict):
            raise ValueError('release response must be an object')
    except Exception:
        out["message"] = "无法查询 GitHub，仍可打开公开下载页。不会自动替换。"
        return out
    tag = str(body.get("tag_name") or "").lstrip("v")
    out["latest"] = tag
    if release:
        import re
        def numeric(value):
            return tuple(map(int, value.split('.'))) if re.fullmatch(r'\d+\.\d+\.\d+', value) else None
        latest, installed = numeric(tag), numeric(current)
        if latest and installed and not body.get('prerelease') and not body.get('draft'):
            out['update_available'] = latest > installed
            out['message'] = (f'发现正式版 {tag}，可打开下载页获取安装程序；不会自动替换。' if latest > installed
                              else f'当前 {current} 已是最新可用版本。')
        else:
            out['message'] = '没有查到可比较的正式版本；可打开下载页，当前安装不变。'
        return out
    if tag and tag != APP_VERSION:
        out["message"] = f"公开仓库最新标记 {tag}。预览不会自动下载或覆盖日用。"
    elif tag:
        out["message"] = "公开标记与当前日用版本号相同。预览仍不会自动替换。"
    return out
