"""
GitHub Releases 检查与 Windows 单文件 exe 就地替换（下载完成后退出，由批处理覆盖并重启）。
源码运行时不替换自身，仅提示前往 Release。

国内网络：默认通过前缀式镜像访问 api.github.com 与 release 附件下载地址。
- 环境变量 DT_GITHUB_MIRROR：自定义镜像前缀，例如 https://ghproxy.com 或 https://mirror.ghproxy.com
- 设为 0 / false / off / direct / none 则直连 GitHub（不走镜像）。
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

from app_version import APP_VERSION, GITHUB_REPO_NAME, GITHUB_REPO_OWNER
from paths import app_root

GITHUB_API_LATEST = (
    f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
)
GITHUB_RELEASES_PAGE = (
    f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
)

# 常见 ghproxy 类前缀；不可用时可改此常量或设 DT_GITHUB_MIRROR。
DEFAULT_GITHUB_MIRROR_PREFIX = "https://ghproxy.com"

_GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "DoubaoTypeless-updater",
}


def _mirror_disabled_token(s: str) -> bool:
    return s.strip().lower() in ("0", "false", "no", "off", "none", "direct", "-")


def effective_github_mirror_prefix() -> str | None:
    """返回镜像前缀（无尾部斜杠），无镜像时返回 None。"""
    raw = os.environ.get("DT_GITHUB_MIRROR")
    if raw is None:
        p = (DEFAULT_GITHUB_MIRROR_PREFIX or "").strip().rstrip("/")
        return p or None
    s = raw.strip()
    if not s or _mirror_disabled_token(s):
        return None
    return s.rstrip("/")


def mirror_github_url(url: str) -> str:
    """将官方 GitHub URL 转为 前缀/完整URL 形式（与 ghproxy 类服务兼容）。"""
    prefix = effective_github_mirror_prefix()
    if not prefix or not (url or "").strip():
        return url
    u = url.strip()
    if u.startswith(prefix + "/"):
        return u
    return f"{prefix}/{u}"


def normalize_version_tuple(s: str) -> tuple[int, ...]:
    s = (s or "").strip().lstrip("vV")
    if not s:
        return (0,)
    parts: list[int] = []
    for seg in re.split(r"[^\d]+", s):
        if seg.isdigit():
            parts.append(int(seg))
    return tuple(parts) if parts else (0,)


def remote_is_newer(remote_tag: str, current: str = APP_VERSION) -> bool:
    return normalize_version_tuple(remote_tag) > normalize_version_tuple(current)


async def fetch_latest_release() -> dict[str, Any] | None:
    api_url = mirror_github_url(GITHUB_API_LATEST)
    async with httpx.AsyncClient(timeout=20.0, headers=_GH_HEADERS) as client:
        r = await client.get(api_url)
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None


def pick_exe_asset(assets: list[Any]) -> dict[str, Any] | None:
    if not isinstance(assets, list):
        return None
    for a in assets:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name", "")).lower()
        url = a.get("browser_download_url")
        if not url or not isinstance(url, str):
            continue
        if name.endswith(".exe") and "doubao" in name:
            return a
    for a in assets:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name", "")).lower()
        url = a.get("browser_download_url")
        if url and isinstance(url, str) and name.endswith(".exe"):
            return a
    return None


async def download_to_path(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=30.0),
            headers=_GH_HEADERS,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    async for chunk in r.aiter_bytes():
                        f.write(chunk)
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        tmp.rename(dest)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def write_update_bat(current_exe: Path, downloaded_exe: Path) -> Path:
    """当前进程退出后：删旧 exe，把新文件 move 成同名并启动。"""
    bat = app_root() / "_DoubaoTypeless_update.bat"
    exe_name = current_exe.name
    cur = str(current_exe.resolve())
    newf = str(downloaded_exe.resolve())
    # 批处理里路径用引号；% 在 bat 中有含义，替换为 %%
    cur_esc = cur.replace("%", "%%")
    new_esc = newf.replace("%", "%%")
    bat.write_text(
        "\n".join(
            [
                "@echo off",
                "chcp 65001 >nul",
                "timeout /t 2 /nobreak >nul",
                ":wait",
                f'tasklist /FI "IMAGENAME eq {exe_name}" 2>nul | find /I "{exe_name}" >nul',
                "if %errorlevel%==0 (",
                "  timeout /t 1 /nobreak >nul",
                "  goto wait",
                ")",
                f'del /f /q "{cur_esc}" 2>nul',
                f'move /y "{new_esc}" "{cur_esc}"',
                f'start "" "{cur_esc}"',
                "del \"%~f0\"",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return bat


def launch_update_bat(bat: Path) -> bool:
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat)],
            cwd=str(bat.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
        return True
    except Exception:
        return False


async def run_update_flow(*, log) -> str:
    """
    执行检查与可选下载。返回给人看的摘要（也可用于日志）。
    若已启动更新批处理，返回字符串含 [EXIT] 供调用方退出进程。
    """
    mp = effective_github_mirror_prefix()
    log(f"[update] GitHub: {'镜像 ' + mp if mp else '直连官方'}")

    data = await fetch_latest_release()
    if not data:
        return "无法连接 GitHub 或未找到最新 Release，请稍后重试。"

    tag = str(data.get("tag_name", "")).strip()
    if not tag:
        return "Release 数据异常（无 tag）。"

    if not remote_is_newer(tag, APP_VERSION):
        return f"当前已是最新（本机 v{APP_VERSION}，远端 {tag}）。"

    releases_page = mirror_github_url(GITHUB_RELEASES_PAGE)
    assets = data.get("assets") or []
    asset = pick_exe_asset(assets)
    if not asset:
        return (
            f"发现新版本 {tag}，但未找到 exe 附件。请浏览器打开：\n{releases_page}"
        )

    url = asset.get("browser_download_url")
    if not url:
        return f"发现新版本 {tag}，但下载地址无效。请访问：\n{releases_page}"

    if not getattr(sys, "frozen", False):
        return (
            f"发现新版本 {tag}（当前源码运行 v{APP_VERSION}）。\n"
            f"请 git pull 或下载：\n{releases_page}"
        )

    current = Path(sys.executable).resolve()
    dest = current.parent / f"{current.stem}.new{current.suffix}"
    dl = mirror_github_url(str(url))
    log(f"[update] 下载 {tag} -> {dest.name}")
    try:
        await download_to_path(dl, dest)
    except Exception as e:
        return f"下载失败：{e}"

    if not dest.is_file() or dest.stat().st_size < 64 * 1024:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        return "下载文件异常（过小或不存在），已放弃更新。"

    bat = write_update_bat(current, dest)
    if not launch_update_bat(bat):
        return "无法启动更新脚本，请手动关闭程序后替换 exe。"

    return f"[EXIT] 已下载 {tag}，即将退出以完成更新（请勿手动删 {dest.name}）。"


def check_update_sync_blocking(*, log) -> str:
    """无事件循环时（极少）使用。"""
    return asyncio.run(run_update_flow(log=log))
