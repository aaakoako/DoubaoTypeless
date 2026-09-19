"""Pairing and action grants. Network messages never carry key scripts."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import quote


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


@dataclass
class PairingChallenge:
    long_code: str
    short_code: str
    expires_at: float


def device_label(device_id: str, nicknames: dict | None, index: int) -> str:
    nick = str((nicknames or {}).get(device_id) or "").strip()
    return nick or f"手机 {index}"


def pairing_page_url(base_url: str, code: str) -> str:
    base = (base_url or "").rstrip("/") + "/"
    return f"{base}?pair={quote(code or '', safe='')}"


class AuthService:
    def __init__(self, *, pairing_ttl_s: float = 120, session_ttl_s: float = 8 * 3600):
        self.pairing_ttl_s = pairing_ttl_s
        self.session_ttl_s = session_ttl_s
        self._challenge: PairingChallenge | None = None
        self.sessions: dict[str, Session] = {}

    def current_pairing_challenge(self) -> str | None:
        challenge = self._live_challenge()
        return None if challenge is None else challenge.long_code

    def current_short_code(self) -> str | None:
        challenge = self._live_challenge()
        return None if challenge is None else challenge.short_code

    def _live_challenge(self) -> PairingChallenge | None:
        if not self._challenge:
            return None
        if time.monotonic() > self._challenge.expires_at:
            self._challenge = None
            return None
        return self._challenge

    def pairing_remaining_s(self) -> float:
        challenge = self._live_challenge()
        if challenge is None:
            return 0.0
        return max(0.0, challenge.expires_at - time.monotonic())

    def new_pairing_challenge(self) -> str:
        existing = self.current_pairing_challenge()
        if existing:
            return existing
        self._challenge = PairingChallenge(
            long_code=secrets.token_urlsafe(8),
            short_code=f"{secrets.randbelow(10000):04d}",
            expires_at=time.monotonic() + self.pairing_ttl_s,
        )
        return self._challenge.long_code

    def rotate_pairing_challenge(self) -> str:
        self._challenge = None
        return self.new_pairing_challenge()

    def complete_pairing(self, code: str, *, allow_insert: bool = False, allow_capture: bool = False) -> Session:
        if not self._challenge:
            raise ValueError("no pairing challenge")
        expected = self._challenge
        self._challenge = None
        if time.monotonic() > expected.expires_at:
            raise ValueError("pairing expired")
        offered = (code or "").strip()
        long_ok = len(offered) == len(expected.long_code) and hmac.compare_digest(expected.long_code, offered)
        short_ok = len(offered) == 4 and hmac.compare_digest(expected.short_code, offered)
        if not (long_ok or short_ok):
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

    def set_grants(
        self,
        session_id: str,
        *,
        allow_insert: bool | None = None,
        allow_capture: bool | None = None,
    ) -> Session:
        session = self.sessions.get(session_id)
        if session is None or time.time() > session.expires_at:
            raise ValueError("session missing")
        if allow_insert is not None:
            session.allow_insert = bool(allow_insert)
        if allow_capture is not None:
            session.allow_capture = bool(allow_capture)
        return session

    def public_sessions(self) -> list[dict]:
        return [
            {
                "session_id": s.session_id,
                "device_id": s.device_id,
                "allow_insert": s.allow_insert,
                "allow_capture": s.allow_capture,
                "allow_sync": s.allow_sync,
            }
            for s in self.sessions.values()
            if time.time() <= s.expires_at
        ]

    def revoke(self, session_id: str) -> bool:
        return self.sessions.pop(session_id, None) is not None

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
