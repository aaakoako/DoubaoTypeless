"""Capture privacy, region cancel, and rate-limit."""
from __future__ import annotations

import io
import time

import pytest
from PIL import Image

from doubao_typeless.services.capture import CaptureService, MIN_INTERVAL_S, REQUEST_TTL_S
from doubao_typeless.storage.credentials import Session


def _session(**kw) -> Session:
    data = dict(device_id="d", session_id="s", token_hash="h", expires_at=9e12, allow_capture=True)
    data.update(kw)
    return Session(**data)


def test_region_cancel_does_not_grab():
    grabs = []

    def grab(scope):
        grabs.append(scope)
        return b"\x89PNG\r\n\x1a\n"

    svc = CaptureService(grab=grab)
    session = _session()
    svc.begin(session, "region:10,10,80,80", "r1", now=0)
    svc.cancel("r1")
    with pytest.raises(ValueError, match="cancelled"):
        svc.complete("r1", session, now=1)
    assert grabs == []


def test_expired_and_rate_limited_and_hwnd_rejected():
    grabs = []
    svc = CaptureService(grab=lambda s: grabs.append(s) or b"\x89PNG\r\n\x1a\n")
    session = _session()
    with pytest.raises(ValueError, match="unknown"):
        svc.capture(session, "hwnd:99")
    svc.begin(session, "primary", "late", now=0)
    with pytest.raises(ValueError, match="expired"):
        svc.complete("late", session, now=REQUEST_TTL_S + 1)
    assert svc.capture(session, "primary", now=100).startswith(b"\x89PNG")
    with pytest.raises(ValueError, match="rate limited"):
        svc.capture(session, "primary", now=100 + MIN_INTERVAL_S - 0.1)
    assert grabs == ["primary"]


def test_revoke_capture_after_begin():
    svc = CaptureService(grab=lambda _s: b"\x89PNG\r\n\x1a\n")
    session = _session()
    svc.begin(session, "primary", "x", now=0)
    session.allow_capture = False
    with pytest.raises(ValueError, match="not granted"):
        svc.complete("x", session, now=1)


def test_scope_parser_physical_pixels():
    from doubao_typeless.platform.windows.capture import parse_scope

    x, y, r, b = parse_scope("region:-100,20,64,48")
    assert (x, y, r - x, b - y) == (-100, 20, 64, 48)
    with pytest.raises(ValueError):
        parse_scope("hwnd:1")
