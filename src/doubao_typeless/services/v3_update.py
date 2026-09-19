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
    return f"{APP_VERSION} · V3 预览"


def check_preview_update(*, get_json: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "channel": CHANNEL,
        "current": APP_VERSION,
        "label": preview_version_label(),
        "page": DOWNLOAD_PAGE,
        "latest": "",
        "auto_replace": False,
        "writes_daily_use": False,
        "message": "这是隔离预览。只打开公开下载页，不会覆盖日用安装或本预览目录。",
    }
    if get_json is None:
        return out
    try:
        body = get_json(API_LATEST) or {}
    except Exception:
        out["message"] = "无法查询 GitHub，仍可打开公开下载页。不会自动替换。"
        return out
    tag = str(body.get("tag_name") or "").lstrip("v")
    out["latest"] = tag
    if tag and tag != APP_VERSION:
        out["message"] = f"公开仓库最新标记 {tag}。预览不会自动下载或覆盖日用。"
    elif tag:
        out["message"] = "公开标记与当前日用版本号相同。预览仍不会自动替换。"
    return out
