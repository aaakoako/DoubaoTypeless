"""BYOK secrets stay out of settings.json. Windows uses Credential Manager; tests/Linux use the isolated data dir."""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

SERVICE = "DoubaoTypelessV3Preview"
_MEMORY: dict[str, str] = {}


def _target(data_dir: Path, name: str) -> str:
    digest = hashlib.sha256(str(Path(data_dir).resolve()).encode("utf-8")).hexdigest()[:16]
    return f"{SERVICE}/{digest}/{name}"


def _file_path(data_dir: Path, name: str) -> Path:
    return Path(data_dir) / "secrets" / f"{name}.txt"


def put_secret(data_dir: Path, name: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        delete_secret(data_dir, name)
        return "cleared"
    if sys.platform == "win32" and os.environ.get("DT_V3_SECRET_FILE") != "1":
        try:
            import win32cred

            win32cred.CredWrite(
                {
                    "Type": win32cred.CRED_TYPE_GENERIC,
                    "TargetName": _target(data_dir, name),
                    "UserName": SERVICE,
                    "CredentialBlob": value,
                    "Comment": "isolated V3 preview BYOK",
                },
                0,
            )
            path = _file_path(data_dir, name)
            if path.is_file():
                path.unlink()
            _MEMORY.pop(_target(data_dir, name), None)
            return "os"
        except Exception:
            if os.environ.get("DT_V3_SECRET_FILE") == "1":
                path = _file_path(data_dir, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value, encoding="utf-8")
                return "file"
            _MEMORY[_target(data_dir, name)] = value
            return "memory"
    if os.environ.get("DT_V3_SECRET_FILE") == "1":
        path = _file_path(data_dir, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return "file"
    _MEMORY[_target(data_dir, name)] = value
    return "memory"


def get_secret(data_dir: Path, name: str) -> str:
    if sys.platform == "win32" and os.environ.get("DT_V3_SECRET_FILE") != "1":
        try:
            import win32cred

            blob = win32cred.CredRead(_target(data_dir, name), win32cred.CRED_TYPE_GENERIC)
            raw = blob.get("CredentialBlob") or b""
            if isinstance(raw, bytes):
                return raw.decode("utf-8", errors="replace").strip()
            return str(raw).strip()
        except Exception:
            mem = _MEMORY.get(_target(data_dir, name), "")
            if mem:
                return mem
    if os.environ.get("DT_V3_SECRET_FILE") == "1":
        path = _file_path(data_dir, name)
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    return _MEMORY.get(_target(data_dir, name), "")


def delete_secret(data_dir: Path, name: str) -> None:
    if sys.platform == "win32":
        try:
            import win32cred

            win32cred.CredDelete(_target(data_dir, name), win32cred.CRED_TYPE_GENERIC)
        except Exception:
            pass
    path = _file_path(data_dir, name)
    if path.is_file():
        path.unlink()
    _MEMORY.pop(_target(data_dir, name), None)
