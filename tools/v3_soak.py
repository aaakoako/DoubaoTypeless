"""200-round protocol soak: chunked upload + freeze + images-then-text, zero Enter."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EVIDENCE = ROOT / "docs" / "evidence" / "v3-soak"

ROUNDS = 200


def png(color, label) -> bytes:
    buf = io.BytesIO()
    image = Image.new("RGB", (64, 48), color)
    image.save(buf, format="PNG")
    return buf.getvalue()


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    from doubao_typeless.core.attempt import Attempt
    from doubao_typeless.core.bundle import Draft, freeze_bundle
    from doubao_typeless.services.assets import UploadService
    from doubao_typeless.services.delivery import DeliveryService, VK_RETURN
    from doubao_typeless.storage.asset_store import AssetStore
    from doubao_typeless.storage.db import V3DB

    store = AssetStore(EVIDENCE / "assets")
    db = V3DB(EVIDENCE / "soak.sqlite")
    uploads = UploadService(store, db)
    log_path = EVIDENCE / "rounds.jsonl"
    if log_path.exists():
        log_path.unlink()
    failures = []
    enter = 0
    t0 = time.perf_counter()
    for i in range(ROUNDS):
        a = png((20 + i % 80, 80, 90), f"A{i}")
        b = png((90, 20 + i % 80, 40), f"B{i}")
        metas = []
        for blob in (a, b):
            digest = hashlib.sha256(blob).hexdigest()
            sess = uploads.init(mime="image/png", total_bytes=len(blob), sha256=digest, width=64, height=48)
            uploads.put_chunk(sess["upload_id"], 0, blob)
            metas.append(uploads.complete(sess["upload_id"]))
        draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 1, "phone", f"soak-{i}\nsecond line", assets=metas)
        bundle = freeze_bundle(draft, bundle_id=str(uuid.uuid4()))
        draft.text = "must-not-leak"
        texts = []
        images = []
        pasted = []

        def paste():
            pasted.append("paste")

        svc = DeliveryService(
            paste=paste,
            set_clipboard_image=lambda data: images.append(hashlib.sha256(data).hexdigest()),
            set_clipboard_text=lambda text: texts.append(text),
            read_focus=lambda: ("ComposerPane", "chatinput"),
            observe_image=lambda: "observed",
            observe_text=lambda: "observed",
            send_key=lambda vk, _up: failures.append("enter") if vk == VK_RETURN else None,
        )
        attempt = Attempt(str(uuid.uuid4()), str(uuid.uuid4()), bundle["bundle_id"], "soak")
        hydrated = dict(bundle)
        hydrated["assets"] = [
            {**m, "bytes_data": store.get(m["asset_id"])} for m in metas
        ]
        out = svc.run(attempt, hydrated)
        db.record_bundle(bundle, attempt_result=out.result)
        row = {
            "i": i,
            "result": out.result,
            "images": len(images),
            "text": texts[-1] if texts else None,
            "frozen": bundle["text"],
            "enter": svc.enter_count,
        }
        if out.result != "CONFIRMED" or row["text"] != f"soak-{i}\nsecond line" or len(images) != 2:
            failures.append(row)
        log_path.open("a", encoding="utf-8").write(json.dumps(row, ensure_ascii=False) + "\n")
    elapsed = time.perf_counter() - t0
    result = {
        "case_id": "AC3-083",
        "status": "PASS" if not failures else "FAIL",
        "rounds": ROUNDS,
        "failures": failures[:10],
        "failure_count": len(failures),
        "elapsed_s": elapsed,
        "sqlite": str(EVIDENCE / "soak.sqlite"),
        "note": "Windows 协议浸泡：分块上传+冻结+先图后文。不是真机 2 小时语音/截屏矩阵。",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (EVIDENCE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "rounds", "failure_count", "elapsed_s")}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
