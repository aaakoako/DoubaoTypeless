"""BYOK keeps original text; UNKNOWN insert asks RecoveryDialog, no auto replay."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from doubao_typeless.app import V3App
from doubao_typeless.core.attempt import Attempt, Step
from doubao_typeless.services.byok import ByokService, ERROR_LABELS
from doubao_typeless.ui.desktop import RecoveryDialog, apply_ui_font
from doubao_typeless.ui.recovery import plan_retry

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "v3-d2"


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    asked: list[str] = []

    def boom(_url, _body, _headers):
        raise TimeoutError("timeout waiting")

    svc = ByokService(endpoint="https://example.invalid/v1", api_key="sk-not-used", post=boom)
    polished = svc.polish("原文必须留下", draft_id="d", revision=1, current_draft_id="d", current_revision=1)
    plan = plan_retry(
        previous_result="UNKNOWN",
        same_target=True,
        images_observed=0,
        images_total=1,
        text_sent=False,
    )
    app = V3App(data_dir=EVIDENCE / "byok-data", port=0)
    app.ui_hook = lambda event, **_k: asked.append(event)
    app.draft.text = "待恢复"
    app.bridge.last_bundle = {"bundle_id": "b1", "text": "待恢复", "assets": []}
    app._last_attempt = Attempt("a1", "i1", "b1", "generic_text")
    app._last_attempt.result = "UNKNOWN"
    app._last_attempt.steps = [Step(0, "text", None, "unknown", "none")]
    app.insert_last()
    from PySide6.QtWidgets import QApplication

    qt = QApplication.instance() or QApplication([])
    apply_ui_font(qt)
    dlg = RecoveryDialog()
    dlg._pick(dlg._dlg, "text_only")
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "byok_status": polished["status"],
        "byok_text": polished["text"],
        "byok_message": polished.get("message"),
        "labels_keep_original": "原文" in ERROR_LABELS["timeout"],
        "plan_mode": plan["mode"],
        "auto_replay": plan["auto_replay"],
        "ui_asked": asked,
        "recovery_choice": dlg.choice,
        "cursor_claimed": False,
    }
    payload["ok"] = (
        polished["status"] == "error"
        and polished["text"] == "原文必须留下"
        and plan["mode"] == "ask"
        and plan["auto_replay"] is False
        and "recovery_ask" in asked
        and dlg.choice == "text_only"
    )
    (EVIDENCE / "byok_recovery.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "byok": polished["status"], "asked": asked, "choice": dlg.choice}, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
