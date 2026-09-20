"""有限范围内的 Composer 结构识别，不凭进程名/整页文字猜输入框。"""
from __future__ import annotations
import time

ADD = {"add files", "attach files", "attach", "upload files", "add photos & files", "add photos and files",
       "添加文件", "附加文件", "上传文件", "添加照片和文件", "添加照片与文件", "添加附件"}
SEND = {"send", "send message", "submit", "发送", "发送消息"}
VOICE = {"use voice mode", "start voice mode", "voice mode", "use voice", "dictate", "语音模式", "使用语音模式", "使用语音", "听写"}


def role_for_button(name: str, automation_id: str = "") -> str:
    text = " ".join(name.lower().split())
    identity = automation_id.lower()
    if text in ADD or any(x in identity for x in ("attach-button", "upload-button", "add-files")):
        return "add"
    if text in SEND or any(x in identity for x in ("send-button", "send-message")):
        return "send"
    if text in VOICE or "voice-mode-button" in identity:
        return "voice"
    return ""


def attachment_remove(name: str, automation_id: str = "") -> bool:
    text = " ".join(name.lower().split())
    identity = automation_id.lower()
    if any(t in identity for t in ("remove-attachment", "remove-file", "remove-image", "delete-attachment")):
        return True
    remove = any(t in text for t in ("remove", "delete", "移除", "删除"))
    material = any(t in text for t in ("attachment", "image", "photo", "file", "附件", "图片", "照片", "文件"))
    return remove and material


def valid_scope(records: list[dict], focused_id, *, complete: bool) -> bool:
    if not complete:
        return False
    editors = []
    roles = set()
    for d in records:
        editable = d.get("control_type") == 50004 or d.get("value_editable") is True
        editable |= d.get("control_type") == 50030 and d.get("keyboard_focusable") is True and d.get("readonly") is False
        if editable and d.get("enabled") and not d.get("offscreen"):
            if d.get("password") or d.get("readonly") is True:
                return False
            identity = (str(d.get("automation_id", "")) + " " + str(d.get("class_name", ""))).lower()
            if any(t in identity for t in ("search", "monaco", "scintilla", "terminal", "password")):
                return False
            editors.append(tuple(d.get("runtime_id") or []))
        if d.get("control_type") == 50000 and not d.get("offscreen"):
            roles.add(role_for_button(str(d.get("name") or ""), str(d.get("automation_id") or "")))
    return (editors == [tuple(focused_id)] and "add" in roles and bool(roles & {"send", "voice"}))


def find_structural_scope(uia, chain):
    """最近、完整扫描、唯一输入框与附件/发送按钮，不能扩大到整个Document。"""
    from doubao_typeless.platform.windows.focus import describe, runtime_id
    focus_id = runtime_id(chain[0][0])
    for root, desc in chain[1:6]:
        if desc.get("control_type") in {50030, 50032}:  # 文档或应用根窗口不作为回退容器
            break
        end = time.monotonic() + .12
        todo = [(root, 0)]
        records = []
        complete = True
        while todo:
            if len(records) >= 100 or time.monotonic() > end:
                complete = False; break
            node, depth = todo.pop()
            d = describe(node); d["runtime_id"] = runtime_id(node); records.append(d)
            child = uia.ControlViewWalker.GetFirstChildElement(node)
            if child and depth >= 6:
                complete = False; break
            while child:
                if len(todo) + len(records) >= 100 or time.monotonic() > end:
                    complete = False; break
                todo.append((child, depth + 1)); child = uia.ControlViewWalker.GetNextSiblingElement(child)
            if not complete: break
        if valid_scope(records, focus_id, complete=complete):
            return root
    return None
