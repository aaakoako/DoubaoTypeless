"""Atomic image asset store. Writes temp then replace; never keep source layers in bundle."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
MAX_BYTES = 8 * 1024 * 1024


class AssetStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_png(self, data: bytes, *, width: int, height: int, role: str) -> dict:
        if len(data) > MAX_BYTES:
            raise ValueError("asset too large")
        if not (data.startswith(PNG_MAGIC) or data.startswith(JPEG_MAGIC)):
            raise ValueError("bad magic")
        asset_id = str(uuid.uuid4())
        digest = hashlib.sha256(data).hexdigest()
        dest = self.root / f"{asset_id}.bin"
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
        meta = {
            "asset_id": asset_id,
            "render_revision": 1,
            "sha256": digest,
            "mime": "image/png" if data.startswith(PNG_MAGIC) else "image/jpeg",
            "bytes": len(data),
            "width": width,
            "height": height,
            "role": role,
        }
        meta_path = self.root / f"{asset_id}.meta.json"
        meta_tmp = meta_path.with_suffix(".tmp")
        meta_tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        os.replace(meta_tmp, meta_path)
        return meta

    def get(self, asset_id: str) -> bytes:
        path = self.root / f"{asset_id}.bin"
        if not path.is_file():
            raise FileNotFoundError(asset_id)
        return path.read_bytes()

    def meta(self, asset_id: str) -> dict:
        path = self.root / f"{asset_id}.meta.json"
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return raw
            except json.JSONDecodeError:
                pass
        return {}
