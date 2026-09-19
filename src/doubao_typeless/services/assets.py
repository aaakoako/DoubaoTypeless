"""Chunked asset upload. Files go to temp then atomic replace; DB only after complete."""
from __future__ import annotations

import hashlib
import io
import math
import re
import uuid
from pathlib import Path

from PIL import Image

from doubao_typeless.storage.asset_store import JPEG_MAGIC, MAX_BYTES, PNG_MAGIC, AssetStore
from doubao_typeless.storage.db import V3DB

CHUNK = 512 * 1024
MAX_PIXELS = 48_000_000
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def resolve_asset_refs(store: AssetStore, refs: object) -> list[dict]:
    """Map client asset_refs to completed store objects. Never trust client assets."""
    if not isinstance(refs, list):
        raise ValueError("invalid asset_refs")
    ids: list[str] = []
    for ref in refs:
        if not isinstance(ref, str) or not SAFE_ID.match(ref):
            raise ValueError("invalid asset_ref")
        ids.append(ref)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate asset id")
    resolved: list[dict] = []
    for asset_id in ids:
        try:
            payload = store.get(asset_id)
        except FileNotFoundError as exc:
            raise ValueError("unknown asset_ref") from exc
        image = Image.open(io.BytesIO(payload))
        image.load()
        resolved.append(
            {
                "asset_id": asset_id,
                "render_revision": 1,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "mime": "image/png" if payload.startswith(PNG_MAGIC) else "image/jpeg",
                "bytes": len(payload),
                "width": image.width,
                "height": image.height,
                "role": "photo",
            }
        )
    return resolved


class UploadService:
    def __init__(self, store: AssetStore, db: V3DB, *, chunk_size: int = CHUNK):
        self.store = store
        self.db = db
        self.chunk_size = chunk_size
        self._uploads: dict[str, dict] = {}

    def init(
        self,
        *,
        mime: str,
        total_bytes: int,
        sha256: str,
        width: int,
        height: int,
        chunk_size: int | None = None,
        owner_session_id: str = "",
    ) -> dict:
        if total_bytes <= 0 or total_bytes > MAX_BYTES:
            raise ValueError("asset too large")
        if width * height > MAX_PIXELS:
            raise ValueError("too many pixels")
        if mime not in {"image/png", "image/jpeg"}:
            raise ValueError("bad mime")
        upload_id = uuid.uuid4().hex
        size = int(chunk_size or self.chunk_size)
        expected = max(1, math.ceil(total_bytes / size))
        tmp_dir = self.store.root / "uploads" / upload_id
        tmp_dir.mkdir(parents=True, exist_ok=True)
        self._uploads[upload_id] = {
            "mime": mime,
            "total_bytes": total_bytes,
            "sha256": sha256,
            "width": width,
            "height": height,
            "chunk_size": size,
            "expected": expected,
            "chunks": {},
            "tmp_dir": tmp_dir,
            "completed": None,
            "owner": owner_session_id,
        }
        return {"upload_id": upload_id, "chunk_size": size, "expected_chunks": expected}

    def _session(self, upload_id: str, owner_session_id: str = "") -> dict:
        if not SAFE_ID.match(upload_id or "") or upload_id not in self._uploads:
            raise ValueError("upload id invalid")
        session = self._uploads[upload_id]
        owner = session.get("owner") or ""
        if owner and owner_session_id and owner != owner_session_id:
            raise ValueError("upload owner")
        return session

    def put_chunk(self, upload_id: str, index: int, data: bytes, owner_session_id: str = "") -> None:
        session = self._session(upload_id, owner_session_id)
        if index < 0 or index >= session["expected"]:
            raise ValueError("chunk index")
        if len(session["chunks"]) >= 2 and index not in session["chunks"]:
            # 最多并发2个未完成块：已有未写完的超过2则拒绝新的。已落地块不计入。
            inflight = [i for i in session["chunks"] if not (session["tmp_dir"] / f"{i}.part").is_file()]
            if len(inflight) >= 2:
                raise ValueError("too many concurrent chunks")
        part = session["tmp_dir"] / f"{index}.part"
        tmp = part.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(part)
        session["chunks"][index] = len(data)

    def missing_chunks(self, upload_id: str, owner_session_id: str = "") -> list[int]:
        session = self._session(upload_id, owner_session_id)
        return [i for i in range(session["expected"]) if i not in session["chunks"]]

    def complete(self, upload_id: str, owner_session_id: str = "") -> dict:
        session = self._session(upload_id, owner_session_id)
        if session["completed"]:
            return session["completed"]
        missing = self.missing_chunks(upload_id)
        if missing:
            raise ValueError(f"missing chunks {missing}")
        parts = [ (session["tmp_dir"] / f"{i}.part").read_bytes() for i in range(session["expected"]) ]
        payload = b"".join(parts)
        if len(payload) != session["total_bytes"]:
            self._purge(session)
            raise ValueError("size mismatch")
        digest = hashlib.sha256(payload).hexdigest()
        expected = str(session.get("sha256") or "")
        if expected not in {"", "pending"} and digest != expected:
            self._purge(session)
            raise ValueError("hash mismatch")
        if not (payload.startswith(PNG_MAGIC) or payload.startswith(JPEG_MAGIC)):
            self._purge(session)
            raise ValueError("bad magic")
        image = Image.open(io.BytesIO(payload))
        image.load()
        if image.width * image.height > MAX_PIXELS:
            self._purge(session)
            raise ValueError("too many pixels")
        existing = self.db.asset(digest)
        if existing:
            session["completed"] = {
                "asset_id": existing["asset_id"],
                "render_revision": 1,
                "sha256": digest,
                "mime": session["mime"],
                "bytes": len(payload),
                "width": image.width,
                "height": image.height,
                "role": "photo",
            }
            self._purge(session)
            return session["completed"]
        meta = self.store.put_png(payload, width=image.width, height=image.height, role="photo")
        self.db.upsert_asset(
            meta["asset_id"],
            meta["sha256"],
            meta["bytes"],
            referenced=False,
            owner_session_id=str(session.get("owner") or owner_session_id or ""),
        )
        session["completed"] = meta
        self._purge(session)
        return meta

    def abort(self, upload_id: str) -> None:
        if upload_id in self._uploads:
            self._purge(self._uploads[upload_id])
            del self._uploads[upload_id]

    def _purge(self, session: dict) -> None:
        tmp_dir: Path = session["tmp_dir"]
        if tmp_dir.is_dir():
            for path in tmp_dir.glob("*"):
                path.unlink(missing_ok=True)
            tmp_dir.rmdir()
