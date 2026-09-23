"""手机是工作稿作者，电脑持久保存镜像；确认/重连不得改写手机版本。

同步本身永远不投递。所有身份由鉴权入口补充，所有附件从服务器资产表解析。
"""
from __future__ import annotations

import copy
from typing import Callable

from doubao_typeless.core.bundle import Draft, TEXT_UTF8_LIMIT, source_snapshot
from doubao_typeless.services.draft_assets import resolve_draft_assets


def is_primary(data: dict) -> bool:
    return data.get("authority") == "phone"


def mirror_info(draft: Draft) -> dict:
    return {"authority": draft.authority, "generation": draft.generation,
            "owner_device_id": draft.editor_device_id, **source_snapshot(draft),
            "asset_refs": [a.get("asset_id") for a in draft.assets]}


def apply_phone_snapshot(draft: Draft, data: dict, store,
                         persist: Callable[[Draft], None],
                         preserve: Callable[[Draft], None]) -> dict:
    """原子落盘后才 ACK。重传是幂等操作；同版本不同附件也不能冒充已保存。"""
    if data.get("_source") != "remote" or not data.get("_device_id"):
        raise ValueError("PHONE_SESSION_REQUIRED")
    if data.get("assets") is not None:
        raise ValueError("client assets rejected")
    for name in ("draft_id", "epoch", "update_id"):
        value = data.get(name)
        if not isinstance(value, str) or not value or len(value) > 128:
            raise ValueError("INVALID_PHONE_IDENTITY")
    for name in ("revision", "generation"):
        value = data.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 2**53-1:
            raise ValueError("INVALID_PHONE_VERSION")
    text = data.get("text")
    if not isinstance(text, str) or len(text.encode("utf-8")) > TEXT_UTF8_LIMIT:
        raise ValueError("text byte limit")
    owner = data["_device_id"]
    same = (draft.draft_id, draft.epoch) == (data["draft_id"], data["epoch"])
    replacing_owner = draft.authority == "phone" and draft.editor_device_id != owner
    takeover = data.get("takeover")
    if draft.authority == "phone":
        expected = {"draft_id":draft.draft_id, "epoch":draft.epoch, "revision":draft.revision,
                    "owner_device_id":draft.editor_device_id}
        explicit_switch = isinstance(takeover, dict) and takeover == expected
    else:
        explicit_switch = False
    if replacing_owner and not explicit_switch:
        raise ValueError("OTHER_PHONE_OWNER")
    if draft.authority == "phone" and not replacing_owner and not explicit_switch:
        if data["generation"] < draft.generation:
            raise ValueError("STALE_PHONE_GENERATION")
        if data["generation"] == draft.generation:
            if not same:
                raise ValueError("PHONE_IDENTITY_CONFLICT")
            if data["revision"] < draft.revision:
                raise ValueError("STALE_PHONE_REVISION")
        elif same:
            raise ValueError("PHONE_GENERATION_REQUIRES_NEW_EPOCH")
    elif draft.authority != "phone" and draft.editor_device_id not in {"pc", "phone", owner}:
        # 其他已连接手机的旧稿需要显式切换设备，而不是一次配对即可覆写。
        raise ValueError("OTHER_PHONE_OWNER")

    assets = resolve_draft_assets(store, data, draft.assets)
    incoming = Draft(draft_id=data["draft_id"], epoch=data["epoch"],
                     revision=data["revision"], editor_device_id=owner, text=text,
                     assets=assets, authority="phone", generation=data["generation"])
    identical = (draft.authority == "phone" and draft.editor_device_id == owner
                 and draft.generation == incoming.generation
                 and source_snapshot(draft) == source_snapshot(incoming))
    if (not explicit_switch and draft.authority == "phone" and same and draft.revision == incoming.revision
            and not identical):
        raise ValueError("PHONE_REVISION_CONFLICT")
    if not identical:
        # 旧的独立电脑稿/上一段先保全；同一手机的正常编辑不制造几千份历史。
        if (replacing_owner or not same or draft.authority != "phone") and (draft.text or draft.assets):
            preserve(copy.deepcopy(draft))
        persist(incoming)  # 失败时旧镜像和版本保持不变，绝不发送假的 durable ACK。
        draft.__dict__.update(incoming.__dict__)
    return {"authority": "phone", "draft_id": incoming.draft_id, "epoch": incoming.epoch,
            "revision": incoming.revision, "generation": incoming.generation,
            "update_id": data["update_id"], "durable": True, "parked": False,
            "changed": not identical}
