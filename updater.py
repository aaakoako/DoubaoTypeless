"""
GitHub Releases 检查与 Windows 单文件 exe 就地替换（下载完成后退出，由批处理覆盖并重启）。
源码运行时不替换自身，仅提示前往 Release。

访问策略：**优先直连 GitHub**；失败时再按序尝试国内前缀镜像（ghproxy 等）。
- 环境变量 DT_GITHUB_MIRROR 未设置：直连 → 内置 FALLBACK_MIRROR_PREFIXES。
- 设为 0 / false / off / direct / none：**仅直连**，不回退镜像。
- 设为自定义 URL（如 https://mirror.ghproxy.com）：直连 → 仅该镜像（不再试其它内置镜像）。

打包 exe 启动约 4 秒后会自动预检更新；不需要时设 **DT_SKIP_AUTO_UPDATE_CHECK=1**。
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

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


async def download_to_path(
    url: str,
    dest: Path,
    *,
    progress: Callable[[int, int | None], Any] | None = None,
) -> None:
    """progress(done_bytes, total_bytes_or_none)，从任意线程调用；由调用方负责切回 UI 线程。"""
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
                cl = r.headers.get("content-length")
                total: int | None = None
                if cl is not None and str(cl).isdigit():
                    total = int(cl)
                done = 0
                last_emit = 0.0

                def maybe_emit(force: bool = False) -> None:
                    nonlocal last_emit
                    if not progress:
                        return
                    now = time.monotonic()
                    if (
                        force
                        or now - last_emit >= 0.12
                        or (total is not None and done >= total)
                    ):
                        progress(done, total)
                        last_emit = now

                maybe_emit(force=True)
                with open(tmp, "wb") as f:
                    async for chunk in r.aiter_bytes():
                        f.write(chunk)
                        done += len(chunk)
                        maybe_emit()
                maybe_emit(force=True)
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
    """当前进程退出后：删旧 exe，把新文件 move 成同名并启动。

    PyInstaller 单文件退出后仍会短暂占用/清理 %TEMP%\\_MEI*；若立刻 start 新版本，bootloader
    可能在不完整环境下加载 python*.dll，出现「Failed to load Python DLL / 找不到指定的模块」。
    因此在 tasklist 不再列出本 exe 后**再额外等待数秒**，并用 PowerShell Start-Process 拉起进程
    （失败时回退到 cmd start）。

    关键步骤追加到 exe 同目录下的 ``update.log`` 与 ``debug.log``，便于排查「下载成功但未替换」。
    ``move`` 等失败时复制本脚本为 ``_DoubaoTypeless_update_failed.bat`` 并 **exit /b 1**，不删除自身。
    """
    bat = app_root() / "_DoubaoTypeless_update.bat"
    exe_name = current_exe.name
    cur = str(current_exe.resolve())
    newf = str(downloaded_exe.resolve())
    exe_dir = str(current_exe.parent.resolve())
    # 批处理里路径用引号；% 在 bat 中有含义，替换为 %%
    cur_esc = cur.replace("%", "%%")
    new_esc = newf.replace("%", "%%")
    dir_esc = exe_dir.replace("%", "%%")
    # set "VAR=..." 中的路径同样需转义 %
    cur_set = cur.replace("%", "%%")
    dir_set = exe_dir.replace("%", "%%")
    failed_copy = (
        'copy /y "%~f0" "%DT_LOG_DIR%\\_DoubaoTypeless_update_failed.bat" >nul 2>&1'
    )
    bat.write_text(
        "\n".join(
            [
                "@echo off",
                "chcp 65001 >nul",
                "setlocal EnableDelayedExpansion",
                f'set "DT_LOG_DIR={dir_set}"',
                'set "LOGU=%DT_LOG_DIR%\\update.log"',
                'set "LOGD=%DT_LOG_DIR%\\debug.log"',
                'call :ulog "update bat started"',
                "timeout /t 6 /nobreak >nul",
                ":wait",
                f'tasklist /FI "IMAGENAME eq {exe_name}" 2>nul | find /I "{exe_name}" >nul',
                "if %errorlevel%==0 (",
                "  timeout /t 1 /nobreak >nul",
                "  goto wait",
                ")",
                'call :ulog "old process gone, waiting 8s for _MEI cleanup"',
                "timeout /t 8 /nobreak >nul",
                'call :ulog "deleting old exe (retry on lock)"',
                'set "DEL_N=0"',
                ":del_old",
                f'if not exist "{cur_esc}" goto del_old_done',
                f'del /f /q "{cur_esc}" 2>nul',
                f'if not exist "{cur_esc}" goto del_old_done',
                "set /a DEL_N+=1",
                "if !DEL_N! geq 36 goto del_old_fail",
                'call :ulog "WARN old exe locked, retry !DEL_N!/35 in 2s"',
                "timeout /t 2 /nobreak >nul",
                "goto del_old",
                ":del_old_fail",
                'call :ulog "ERROR del old failed after retries (AV/sync holding file?)"',
                f"  {failed_copy}",
                "  exit /b 1",
                ":del_old_done",
                'call :ulog "moving new exe into place (retry on lock)"',
                'set "MV_N=0"',
                ":mv_new",
                f'move /y "{new_esc}" "{cur_esc}"',
                "if not errorlevel 1 goto mv_ok",
                "set /a MV_N+=1",
                "if !MV_N! geq 26 goto mv_fail",
                'call :ulog "WARN move failed, retry !MV_N!/25 in 2s"',
                "timeout /t 2 /nobreak >nul",
                "goto mv_new",
                ":mv_fail",
                'call :ulog "ERROR move failed after retries"',
                f"  {failed_copy}",
                "  exit /b 1",
                ":mv_ok",
                f'if not exist "{cur_esc}" (',
                '  call :ulog "ERROR target exe missing after move"',
                f"  {failed_copy}",
                "  exit /b 1",
                ")",
                'call :ulog "move OK, pre-launch pause 4s"',
                "timeout /t 4 /nobreak >nul",
                f'set "DT_RESTART_EXE={cur_set}"',
                f'set "DT_RESTART_DIR={dir_set}"',
                'call :ulog "starting new process via PowerShell Start-Process"',
                "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \""
                "try { "
                "Start-Process -LiteralPath $env:DT_RESTART_EXE -WorkingDirectory $env:DT_RESTART_DIR; "
                "exit 0 "
                "} catch { exit 1 }\"",
                "if errorlevel 1 (",
                '  call :ulog "PowerShell Start-Process failed, trying cmd start"',
                f'  cd /d "{dir_esc}"',
                "  if errorlevel 1 (",
                '    call :ulog "ERROR cd to app dir failed"',
                f"    {failed_copy}",
                "    exit /b 1",
                "  )",
                f'  start "" "{cur_esc}"',
                ")",
                'call :ulog "update script finished OK, removing bat"',
                "endlocal",
                'del "%~f0"',
                "exit /b 0",
                "",
                ":ulog",
                '>>"%LOGU%" echo %date% %time% [update] %~1',
                '>>"%LOGD%" echo %date% %time% [update] %~1',
                "exit /b",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return bat


def _win32_updater_creation_flags() -> int:
    """
    PyInstaller onefile 在 Windows 上常把进程放进 Job Object，并在主进程退出时结束同 Job 内子进程。
    若更新脚本由 cmd 以默认方式拉起，会在「主程序已关、尚未删旧 exe」阶段被一并杀掉，表现为下载后无下文。
    CREATE_BREAKAWAY_FROM_JOB 让 cmd 脱离该 Job，更新批处理才能跑完。参见 Win32 Job Objects 与 PyInstaller 行为。
    """
    if sys.platform != "win32":
        return 0
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    flags |= getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
    return flags


def launch_update_bat(bat: Path, *, log: Callable[[str], Any] | None = None) -> bool:
    try:
        bat = bat.resolve()
        cwd = str(bat.parent.resolve())
        kw: dict[str, Any] = {
            "args": ["cmd.exe", "/c", str(bat)],
            "cwd": cwd,
            "close_fds": True,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kw["creationflags"] = _win32_updater_creation_flags()
        subprocess.Popen(**kw)
        if log:
            log(
                "[update] 已启动后台更新脚本（CREATE_BREAKAWAY_FROM_JOB，避免随主进程被 Job 结束）"
            )
        return True
    except Exception as e:
        if log:
            log(f"[update] 启动更新脚本失败: {e}")
        return False


async def run_update_precheck(*, log) -> tuple[str, dict[str, Any]]:
    """
    拉取 Release 并判断下一步。
    返回 (kind, payload)：
    - ("show", {"message": str}) 仅展示文案即可（已最新 / 网络失败 / 源码提示等）
    - ("frozen", {"tag", "url", "releases_page"}) 打包 exe 可下载替换，需用户确认后再 execute_frozen_exe_update
    """
    fb = mirror_fallback_prefixes()
    log(
        "[update] 策略: 优先直连 GitHub"
        + (f"，失败则试镜像 {fb}" if fb else "（不回退镜像，已禁用）")
    )

    data, meta_via_prefix = await fetch_latest_release(log=log)
    if not data:
        return ("show", {"message": "无法连接 GitHub 或未找到最新 Release，请稍后重试。"})

    tag = str(data.get("tag_name", "")).strip()
    if not tag:
        return ("show", {"message": "Release 数据异常（无 tag）。"})

    if not remote_is_newer(tag, APP_VERSION):
        return (
            "show",
            {"message": f"当前已是最新（本机 v{APP_VERSION}，远端 {tag}）。"},
        )

    releases_page = (
        GITHUB_RELEASES_PAGE
        if meta_via_prefix is None
        else apply_mirror_prefix(GITHUB_RELEASES_PAGE, meta_via_prefix)
    )
    assets = data.get("assets") or []
    asset = pick_exe_asset(assets)
    if not asset:
        return (
            "show",
            {
                "message": (
                    f"发现新版本 {tag}，但未找到 exe 附件。请浏览器打开：\n{releases_page}"
                )
            },
        )

    url = asset.get("browser_download_url")
    if not url:
        return (
            "show",
            {"message": f"发现新版本 {tag}，但下载地址无效。请访问：\n{releases_page}"},
        )

    if not getattr(sys, "frozen", False):
        return (
            "show",
            {
                "message": (
                    f"发现新版本 {tag}（当前源码运行 v{APP_VERSION}）。\n"
                    f"请 git pull 或下载：\n{releases_page}"
                )
            },
        )

    return (
        "frozen",
        {"tag": tag, "url": str(url), "releases_page": releases_page},
    )


async def execute_frozen_exe_update(
    *,
    tag: str,
    asset_url: str,
    log,
    progress: Callable[[int, int | None], Any] | None = None,
) -> str:
    """已确认后：下载 .new.exe、写批处理、返回含 [EXIT] 的文案或错误说明。"""
    current = Path(sys.executable).resolve()
    dest = current.parent / f"{current.stem}.new{current.suffix}"
    dl_urls = _download_url_plan(str(asset_url))
    log(f"[update] 下载 {tag} -> {dest.name}（{len(dl_urls)} 个 URL 依次尝试）")
    last_err: Exception | None = None
    for i, du in enumerate(dl_urls):
        try:
            log(f"[update] 下载尝试 {i + 1}/{len(dl_urls)}")
            if progress:
                progress(0, None)
            await download_to_path(du, dest, progress=progress)
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
    if not launch_update_bat(bat, log=log):
        return "无法启动更新脚本，请手动关闭程序后替换 exe。"

    return f"[EXIT] 已下载 {tag}，即将退出以完成更新（请勿手动删 {dest.name}）。"


async def run_update_flow(*, log) -> str:
    """
    执行检查与可选下载（无 UI 确认，供脚本 / test_update 使用）。
    若已启动更新批处理，返回字符串含 [EXIT] 供调用方退出进程。
    """
    kind, payload = await run_update_precheck(log=log)
    if kind == "show":
        return str(payload.get("message", ""))
    return await execute_frozen_exe_update(
        tag=str(payload["tag"]),
        asset_url=str(payload["url"]),
        log=log,
    )


def check_update_sync_blocking(*, log) -> str:
    """无事件循环时（极少）使用。"""
    return asyncio.run(run_update_flow(log=log))
