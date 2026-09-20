"""从实际步骤描述投递进度，不把“图片贴出”显示成“图文完成”。

只生成状态，不发送按键、不放宽接收证据、不清草稿。
"""
from __future__ import annotations


def summarize_delivery(bundle: dict, payload: dict) -> dict:
    assets = bundle.get("assets") or []
    planned = {a.get("asset_id") for a in assets if a.get("asset_id")}
    steps = payload.get("steps") or []
    images = [s for s in steps if s.get("kind") == "image" and s.get("asset_id") in planned]
    observed = {s["asset_id"] for s in images if s.get("state") == "observed"}
    attempted = {s["asset_id"] for s in images}
    text_steps = [s for s in steps if s.get("kind") == "text"]
    text_required = bool(bundle.get("text"))
    text_state = "not_needed" if not text_required else "not_attempted"
    if text_steps:
        text_state = "observed" if all(s.get("state") == "observed" for s in text_steps) else "attempted_unconfirmed"
    awaiting_image = bool(images and images[-1].get("state") == "unknown"
                          and not text_steps and not payload.get("error_code"))
    if awaiting_image:
        message = f"已尝试插入 {len(attempted)}/{len(assets)} 张图，接收待确认"
        if text_required:
            message += "；文字尚未插入，已保留"
    elif text_state == "not_attempted" and attempted:
        message = f"已尝试 {len(attempted)}/{len(assets)} 张图；文字尚未插入，已保留"
    elif text_state == "attempted_unconfirmed":
        message = f"图片已确认 {len(observed)}/{len(assets)}；文字已发出，接收待确认" if assets else "文字已发出，接收待确认"
    elif payload.get("result") == "CONFIRMED":
        message = "本次图文已确认接收" if assets and text_required else "本次内容已确认接收"
    else:
        message = "本次内容仍保留，请检查目标"
    return {"images_total": len(assets), "images_attempted": len(attempted),
            "images_observed": len(observed), "text_state": text_state,
            "awaiting_image_confirmation": awaiting_image, "message": message}
