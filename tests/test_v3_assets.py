"""Chunked upload, resume, bad magic, and GC protection."""
from __future__ import annotations

import hashlib
import io
import math

import pytest
from PIL import Image

from doubao_typeless.services.assets import CHUNK, UploadService
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.db import V3DB


def _png(width=64, height=64, size_hint=0) -> bytes:
    image = Image.new("RGB", (width, height), (20, 120, 110))
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=False)
    data = buf.getvalue()
    if size_hint and len(data) < size_hint:
        # PNG allows trailing data after IEND for resume-size tests only if we don't
        # use it for complete(); keep real PNG and repeat canvas instead.
        pass
    return data


def test_chunked_resume_completes_once(tmp_path):
    store = AssetStore(tmp_path / "assets")
    db = V3DB(tmp_path / "v3.sqlite")
    svc = UploadService(store, db)
    payload = _png(400, 400)
    digest = hashlib.sha256(payload).hexdigest()
    session = svc.init(
        mime="image/png",
        total_bytes=len(payload),
        sha256=digest,
        width=400,
        height=400,
            chunk_size=math.ceil(len(payload) / 2),
    )
    chunk = session["chunk_size"]
    svc.put_chunk(session["upload_id"], 0, payload[:chunk])
    missing = svc.missing_chunks(session["upload_id"])
    assert missing == [1]
    svc.put_chunk(session["upload_id"], 1, payload[chunk:])
    meta = svc.complete(session["upload_id"])
    assert meta["sha256"] == digest
    assert store.get(meta["asset_id"]) == payload
    again = svc.complete(session["upload_id"])
    assert again["asset_id"] == meta["asset_id"]


def test_bad_magic_and_path_traversal_leave_no_tmp(tmp_path):
    store = AssetStore(tmp_path / "assets")
    db = V3DB(tmp_path / "v3.sqlite")
    svc = UploadService(store, db)
    payload = b"not-an-image" + b"\x00" * 100
    digest = hashlib.sha256(payload).hexdigest()
    session = svc.init(
        mime="image/png",
        total_bytes=len(payload),
        sha256=digest,
        width=1,
        height=1,
    )
    svc.put_chunk(session["upload_id"], 0, payload)
    with pytest.raises(ValueError, match="magic"):
        svc.complete(session["upload_id"])
    assert not list((tmp_path / "assets").glob("*.tmp"))
    with pytest.raises(ValueError, match="upload"):
        svc.put_chunk("../etc/passwd", 0, b"x")


def test_complete_failure_is_not_durable(tmp_path, monkeypatch):
    store = AssetStore(tmp_path / "assets")
    db = V3DB(tmp_path / "v3.sqlite")
    svc = UploadService(store, db)
    payload = _png()
    digest = hashlib.sha256(payload).hexdigest()
    session = svc.init(
        mime="image/png",
        total_bytes=len(payload),
        sha256=digest,
        width=64,
        height=64,
    )
    svc.put_chunk(session["upload_id"], 0, payload)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError):
        svc.complete(session["upload_id"])
    assert db.asset(digest) is None


def test_gc_skips_attempt_referenced_assets(tmp_path):
    db = V3DB(tmp_path / "v3.sqlite")
    db.upsert_asset("keep", "a" * 64, 10, referenced=True)
    db.upsert_asset("drop", "b" * 64, 10, referenced=False, created_at=1)
    removed = db.gc_unreferenced(now=10**10, ttl_s=1, protected_ids={"keep"})
    assert "drop" in removed
    assert "keep" not in removed
    assert db.asset_by_id("keep") is not None


def test_default_chunk_is_512kib_and_owner_is_enforced(tmp_path):
    assert CHUNK == 512 * 1024
    store = AssetStore(tmp_path / "assets")
    db = V3DB(tmp_path / "v3.sqlite")
    svc = UploadService(store, db)
    payload = _png()
    digest = hashlib.sha256(payload).hexdigest()
    session = svc.init(
        mime="image/png",
        total_bytes=len(payload),
        sha256=digest,
        width=64,
        height=64,
        owner_session_id="owner-a",
    )
    svc.put_chunk(session["upload_id"], 0, payload, owner_session_id="owner-a")
    with pytest.raises(ValueError, match="owner"):
        svc.complete(session["upload_id"], owner_session_id="owner-b")
    meta = svc.complete(session["upload_id"], owner_session_id="owner-a")
    assert meta["sha256"] == digest
