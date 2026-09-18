"""Pairing and action grants. Network messages never carry key scripts."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field


@dataclass
class Session:
    device_id: str
    session_id: str
    token_hash: str
    expires_at: float
    allow_sync: bool = True
    allow_capture: bool = False
    allow_insert: bool = False
    used_nonces: dict[str, float] = field(default_factory=dict)
    token: str = ""


class AuthService:
    def __init__(self, *, pairing_ttl_s: float = 120, session_ttl_s: float = 8 * 3600):
        self.pairing_ttl_s = pairing_ttl_s
        self.session_ttl_s = session_ttl_s
        self._challenge: tuple[str, float] | None = None
        self.sessions: dict[str, Session] = {}

    def current_pairing_challenge(self) -> str | None:
        if not self._challenge:
            return None
        code, expiry = self._challenge
        if time.monotonic() > expiry:
            self._challenge = None
            return None
        return code

    def new_pairing_challenge(self) -> str:
        existing = self.current_pairing_challenge()
        if existing:
            return existing
        code = secrets.token_urlsafe(8)
        self._challenge = (code, time.monotonic() + self.pairing_ttl_s)
        return code

    def complete_pairing(self, code: str, *, allow_insert: bool = False, allow_capture: bool = False) -> Session:
        if not self._challenge:
            raise ValueError("no pairing challenge")
        expected, expiry = self._challenge
        self._challenge = None
        if time.monotonic() > expiry:
            raise ValueError("pairing expired")
        if not hmac.compare_digest(expected, code):
            raise ValueError("pairing mismatch")
        token = secrets.token_urlsafe(24)
        session = Session(
            device_id=secrets.token_hex(8),
            session_id=secrets.token_hex(8),
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=time.time() + self.session_ttl_s,
            allow_insert=allow_insert,
            allow_capture=allow_capture,
            token=token,
        )
        self.sessions[session.session_id] = session
        return session

    def authorize(self, session_id: str, token: str, action: str) -> Session:
        session = self.sessions.get(session_id)
        if not session or time.time() > session.expires_at:
            raise ValueError("session expired")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(session.token_hash, digest):
            raise ValueError("bad token")
        allowed = {
            "sync": session.allow_sync,
            "capture": session.allow_capture,
            "insert": session.allow_insert,
        }.get(action, False)
        if not allowed:
            raise ValueError("action not granted")
        return session

    def issue_nonce(self, session: Session) -> str:
        nonce = secrets.token_urlsafe(24)
        session.used_nonces[nonce] = time.time() + 10
        return nonce

    def consume_nonce(self, session: Session, nonce: str) -> None:
        expiry = session.used_nonces.pop(nonce, None)
        if expiry is None or time.time() > expiry:
            raise ValueError("nonce invalid")


def looks_like_key_script(payload: dict) -> bool:
    if any(k in payload for k in ("keys", "vk", "scan_code")):
        return True
    if isinstance(payload.get("x"), (int, float)) and isinstance(payload.get("y"), (int, float)):
        return True
    control = {k: v for k, v in payload.items() if k != "text"}
    blob = str(control).lower()
    return any(token in blob for token in ("sendinput", "keybd_event", "shell", "cmd.exe"))
