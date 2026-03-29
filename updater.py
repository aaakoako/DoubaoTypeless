"""
GitHub Releases 检查与 Windows 单文件 exe 就地替换（下载完成后退出，由批处理覆盖并重启）。
源码运行时不替换自身，仅提示前往 Release。

访问策略：**优先直连 GitHub**；失败时再按序尝试国内前缀镜像（ghproxy 等）。
- 环境变量 DT_GITHUB_MIRROR 未设置：直连 → 内置 FALLBACK_MIRROR_PREFIXES。
- 设为 0 / false / off / direct / none：**仅直连**，不回退镜像。
- 设为自定义 URL（如 https://mirror.ghproxy.com）：直连 → 仅该镜像（不再试其它内置镜像）。
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

# 直连失败时按序尝试的前缀（与 ghproxy 类「前缀/完整 URL」兼容）。
FALLBACK_MIRROR_PREFIXES: tuple[str, ...] = (
    "https://ghproxy.com",
    "https://mirror.ghproxy.com",
)

_GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "DoubaoTypeless-updater",
}


def _mirror_disabled_token(s: str) -> bool:
    return s.strip().lower() in ("0", "false", "no", "off", "none", "direct", "-")


def mirror_fallback_prefixes() -> list[str]:
    """直连失败时使用的镜像前缀列表（不含尾部斜杠）。"""
    raw = os.environ.get("DT_GITHUB_MIRROR")
    if raw is not None:
        s = raw.strip()
        if not s or _mirror_disabled_token(s):
            return []
        return [s.rstrip("/")]
    return [p.strip().rstrip("/") for p in FALLBACK_MIRROR_PREFIXES if p.strip()]


def apply_mirror_prefix(url: str, prefix: str) -> str:
    """prefix + '/' + 原始 URL（ghproxy 类）。"""
    p = prefix.rstrip("/")
    u = (url or "").strip()
    if not p or not u:
        return u
    if u.startswith(p + "/"):
        return u
    return f"{p}/{u}"


def _api_try_plan() -> list[tuple[str, str, str | None]]:
    """(请求 URL, 日志标签, 成功后用于用户链接/下载的镜像前缀或 None 表示直连)."""
    plan: list[tuple[str, str, str | None]] = [
        (GITHUB_API_LATEST, "直连 api.github.com", None),
    ]
    seen = {GITHUB_API_LATEST}
    for prefix in mirror_fallback_prefixes():
        u = apply_mirror_prefix(GITHUB_API_LATEST, prefix)
        if u not in seen:
            seen.add(u)
            plan.append((u, f"镜像 {prefix}", prefix))
    return plan


def _download_url_plan(original: str) -> list[str]:
    """下载：先官方 URL，再各镜像前缀（去重）。"""
    o = (original or "").strip()
    if not o:
        return []
    out: list[str] = [o]
    seen = {o}
    for prefix in mirror_fallback_prefixes():
        u = apply_mirror_prefix(o, prefix)
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


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


async def fetch_latest_release(*, log) -> tuple[dict[str, Any] | None, str | None]:
    """
    拉取 latest release JSON。
    返回 (data, releases_link_mirror_prefix)：后者为 None 表示元数据来自直连，否则为 winning 镜像前缀。
    """
    async with httpx.AsyncClient(timeout=20.0, headers=_GH_HEADERS) as client:
        for url, label, win_prefix in _api_try_plan():
            try:
                log(f"[update] 请求 Release: {label}")
                r = await client.get(url)
                if r.status_code != 200:
                    log(f"[update] {label} HTTP {r.status_code}，换下一源")
                    continue
                data = r.json()
                if isinstance(data, dict):
                    return data, win_prefix
            except Exception as e:
                log(f"[update] {label} 失败: {e}")
    return None, None


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
    fb = mirror_fallback_prefixes()
    log(
        "[update] 策略: 优先直连 GitHub"
        + (f"，失败则试镜像 {fb}" if fb else "（不回退镜像，已禁用）")
    )

    data, meta_via_prefix = await fetch_latest_release(log=log)
    if not data:
        return "无法连接 GitHub 或未找到最新 Release，请稍后重试。"

    tag = str(data.get("tag_name", "")).strip()
    if not tag:
        return "Release 数据异常（无 tag）。"

    if not remote_is_newer(tag, APP_VERSION):
        return f"当前已是最新（本机 v{APP_VERSION}，远端 {tag}）。"

    releases_page = (
        GITHUB_RELEASES_PAGE
        if meta_via_prefix is None
        else apply_mirror_prefix(GITHUB_RELEASES_PAGE, meta_via_prefix)
    )
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
    dl_urls = _download_url_plan(str(url))
    log(f"[update] 下载 {tag} -> {dest.name}（{len(dl_urls)} 个 URL 依次尝试）")
    last_err: Exception | None = None
    for i, du in enumerate(dl_urls):
        try:
            log(f"[update] 下载尝试 {i + 1}/{len(dl_urls)}")
            await download_to_path(du, dest)
            last_err = None
            break
        except Exception as e:
            last_err = e
            log(f"[update] 下载失败: {e}")
    if last_err is not None:
        return f"下载失败：{last_err}"

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
