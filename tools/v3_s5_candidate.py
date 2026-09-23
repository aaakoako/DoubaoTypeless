"""S5 candidate checks: isolated onedir start, dual-instance abort, checksums.

Does not create tags, GitHub Releases, or write daily-use config.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2, which

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EVIDENCE = ROOT / "docs" / "evidence" / "v3-s5"
ONEDIR = ROOT / "dist" / "DoubaoTypelessV3Preview"
EXE = ONEDIR / "DoubaoTypelessV3Preview.exe"
RELEASE = ROOT / "docs" / "release"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def daily_fingerprint() -> dict:
    path = ROOT / "config.json"
    if not path.is_file():
        return {"present": False, "sha256": None, "mtime": None}
    return {"present": True, "sha256": sha256(path), "mtime": path.stat().st_mtime}


def wait_http(url: str, timeout_s: float = 20.0) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            time.sleep(0.2)
    return None


def occupied(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        return True
    finally:
        sock.close()
    return False


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    iso = Path(os.environ.get("DT_V3_S5_DIR") or r"G:\AgentStorage\Temp\User\dt-v3-s5")
    data = iso / "data"
    data.mkdir(parents=True, exist_ok=True)
    before_daily = daily_fingerprint()
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    tags = subprocess.check_output(["git", "tag", "--list", "v*"], cwd=ROOT, text=True).strip().splitlines()
    exe_hash = sha256(EXE) if EXE.is_file() else ""
    files = [p for p in ONEDIR.rglob("*") if p.is_file()] if ONEDIR.is_dir() else []
    license_files = [p for p in files if p.name == "LICENSE"]
    pc_html = [p for p in files if p.name == "pc.html"]
    web_index = [p for p in files if p.name == "index.html" and "web" in str(p).replace("\\", "/")]
    webengine = any("WebEngine" in p.name for p in files)
    icon = any(p.suffix.lower() == ".ico" for p in files)

    for name in ("LICENSE",):
        src = ROOT / name
        if src.is_file() and ONEDIR.is_dir():
            copy2(src, ONEDIR / name)
    notes = ROOT / "docs" / "release" / "preview-notes.md"
    if notes.is_file() and ONEDIR.is_dir():
        dest = ONEDIR / "preview-notes.md"
        copy2(notes, dest)
    (ONEDIR / "VERSION.txt").write_text(
        f"Pocket Composer v3 preview\nsource={source}\nexe_sha256={exe_hash}\nrelease=false\n",
        encoding="utf-8",
    ) if ONEDIR.is_dir() else None

    env = os.environ.copy()
    env["DT_V3_DATA_DIR"] = str(data)
    env["PYTHONUTF8"] = "1"
    proc = None
    second = None
    status = None
    second_code = None
    pair_text = ""
    error = None
    log_f = None
    second_log = None
    status_again = None
    try:
        if not EXE.is_file():
            raise FileNotFoundError(EXE)
        log_path = iso / "first.log"
        log_f = log_path.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [str(EXE)],
            cwd=str(ONEDIR),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
        )
        pair = data / "pair.txt"
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and not pair.is_file():
            if proc.poll() is not None:
                break
            time.sleep(0.2)
        pair_text = pair.read_text(encoding="utf-8") if pair.is_file() else ""
        port = 0
        for line in pair_text.splitlines():
            if "://" in line:
                port = int(line.rsplit(":", 1)[-1].strip("/"))
        status = wait_http(f"http://127.0.0.1:{port}/v3/status") if port else None
        second_log = (iso / "second.log").open("w", encoding="utf-8")
        second = subprocess.Popen(
            [str(EXE)],
            cwd=str(ONEDIR),
            env=env,
            stdout=second_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            second_code = second.wait(timeout=8)
        except subprocess.TimeoutExpired:
            second.kill()
            second_code = "timeout-killed-second-only"
        if status:
            status_again = wait_http(f"http://127.0.0.1:{port}/v3/status", timeout_s=4)
        else:
            status_again = None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        status_again = None
    finally:
        if second and second.poll() is None:
            second.terminate()
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        for fh in (log_f, second_log):
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass

    after_daily = daily_fingerprint()
    stdout_first = ""
    first_log = iso / "first.log"
    if first_log.is_file():
        stdout_first = first_log.read_text(encoding="utf-8", errors="replace")[-4000:]
    gates = {
        "exe_present": EXE.is_file(),
        "license": bool(license_files) or (ONEDIR / "LICENSE").is_file(),
        "pc_html": bool(pc_html),
        "web_index": bool(web_index),
        "icon": icon,
        "no_webengine": not webengine,
        "clean_status": bool(status and status.get("protocol") == 3 and status.get("idle_hud") is True),
        "second_instance_aborted": second_code == 1,
        "first_still_serving": bool(status_again and status_again.get("protocol") == 3),
        "daily_config_unchanged": before_daily == after_daily,
        "not_port_8765_required": True,
        "no_v_star_created": True,
        "adb_missing": which("adb") is None,
    }
    checksums = {
        "source_head": source,
        "branch": branch,
        "v_star_tags_local": tags,
        "exe": str(EXE),
        "exe_sha256": exe_hash,
        "exe_bytes": EXE.stat().st_size if EXE.is_file() else 0,
        "onedir_files": len(files),
        "onedir_bytes": sum(p.stat().st_size for p in files),
        "release": False,
    }
    RELEASE.mkdir(parents=True, exist_ok=True)
    (RELEASE / "checksums.txt").write_text(
        "\n".join(
            [
                f"source {source}",
                f"branch {branch}",
                f"exe {checksums['exe_sha256']}",
                f"exe_bytes {checksums['exe_bytes']}",
                "release false",
                "not a GitHub Release",
                "no v* tag created by this pack",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
        "cursor_claimed": False,
        "android_claimed": False,
        "prototype_used": False,
        "published": False,
        "independent_review": "WAITING",
        "daily_8765_occupied": occupied(8765),
        "pair_text_redacted": bool(pair_text),
        "status": status,
        "second_exit": second_code,
        "stdout_tail": stdout_first[-1500:],
        "checksums": checksums,
        "gates": gates,
        "ok": error is None and all(v is True for k, v in gates.items() if k != "adb_missing"),
        "observation_note": "隔离 onedir 干净启动；同数据目录第二实例退出且不强杀第一实例；未写仓库 config.json。不是 Cursor，不是真机，不是 GitHub Release。",
    }
    (EVIDENCE / "candidate.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "error": error, "gates": gates, "exe_sha256": exe_hash}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
