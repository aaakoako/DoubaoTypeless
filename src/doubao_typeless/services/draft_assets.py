"""把手机素材文档解析为服务器认可的草稿附件，不接收像素/路径对象。"""
from __future__ import annotations
import copy
from doubao_typeless.services.assets import resolve_asset_refs

ALLOWED_STATUS = {"queued", "editing", "ready", "failed", "dirty"}


def resolve_draft_assets(store, data: dict, current: list[dict]) -> list[dict]:
    if data.get("assets") is not None:
        raise ValueError("client assets rejected")
    refs = data.get("asset_refs")
    docs = data.get("asset_documents")
    if docs is not None:
        if not isinstance(docs, list) or len(docs) > 6:
            raise ValueError("invalid asset documents")
        out, local_ids, document_refs = [], set(), []
        for doc in docs:
            if not isinstance(doc, dict):
                raise ValueError("invalid asset document")
            local_id = doc.get("id")
            if not isinstance(local_id, str) or not local_id or len(local_id) > 512 or local_id in local_ids:
                raise ValueError("invalid local asset identity")
            local_ids.add(local_id)
            aid = doc.get("asset_id") or ""
            status = str(doc.get("status") or "ready")
            version = doc.get("render_revision", 1)
            caption = doc.get("caption") or ""
            if status not in ALLOWED_STATUS or not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise ValueError("invalid asset version")
            if not isinstance(caption, str) or len(caption.encode("utf-8")) > 8192:
                raise ValueError("invalid caption")
            if aid:
                item = resolve_asset_refs(store, [aid])[0]
                document_refs.append(aid)
            else:
                if status == "ready":
                    raise ValueError("IMAGE_NOT_UPLOADED")
                item = {"asset_id": "", "role": "pending", "bytes": 0}
            item.update(local_id=local_id, status=status, render_revision=version, caption=caption)
            out.append(item)
        if refs is not None and refs != document_refs:
            raise ValueError("asset refs/document mismatch")
        return out
    if refs is None:
        return copy.deepcopy(current)
    resolved = resolve_asset_refs(store, refs)
    old = {a.get("asset_id"): a for a in current}
    captions = data.get("captions")
    statuses = data.get("asset_status")
    for i, item in enumerate(resolved):
        prior = old.get(item["asset_id"], {})
        for key in ("caption", "local_id", "status", "render_revision"):
            if key in prior:
                item[key] = prior[key]
        if isinstance(captions, list) and i < len(captions):
            item["caption"] = str(captions[i] or "")
        if isinstance(statuses, list) and i < len(statuses):
            if statuses[i] not in ALLOWED_STATUS:
                raise ValueError("invalid asset status")
            item["status"] = statuses[i]
    return resolved
