"""Cursor Composer adapter. UIA observation is required for CONFIRMED; otherwise UNKNOWN."""
from __future__ import annotations
import time

from doubao_typeless.core.policy import classify_focus

try:
    import win32gui
except ImportError:  # pragma: no cover
    win32gui = None


COMPOSER_HINTS = ("composer", "chatinput", "promptinput", "aicreator")
CODE_HINTS = ("scintilla", "editordocument", "monaco", "codeditor")


def identify(class_name: str, control_type: str = "", automation_id: str = "") -> str:
    kind = classify_focus(class_name, control_type, automation_id)
    if kind == "composer":
        return "cursor_windows"
    if kind == "code":
        return "unsupported_code"
    return "generic_text"


def cursor_windows() -> list[dict]:
    if win32gui is None:
        return []
    found: list[dict] = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if "cursor" in title.lower() or class_name.startswith("Chrome_WidgetWin"):
            if title:
                found.append({"hwnd": int(hwnd), "title": title, "class_name": class_name})
        return True

    win32gui.EnumWindows(cb, None)
    return [w for w in found if "cursor" in w["title"].lower()]


def _element_by_id(uia, root, expected, *, limit=600):
    """只查已绑定的窗口/容器，限制数量/时间；不匹配控件正文。"""
    from doubao_typeless.platform.windows.focus import runtime_id
    todo=[root];n=0;end=time.monotonic()+.65
    while todo and n<limit and time.monotonic()<end:
        node=todo.pop();n+=1
        if runtime_id(node)==tuple(expected):return node
        child=uia.ControlViewWalker.GetFirstChildElement(node)
        while child and len(todo)+n<limit and time.monotonic()<end:
            todo.append(child);child=uia.ControlViewWalker.GetNextSiblingElement(child)
    return None


def _probe_uia_direct(anchor=None) -> dict:
    """只在确定的Composer容器采样；焦点进附件时仍用原容器，不扫描历史消息。"""
    report={"focus":None,"composer_control":None,"image_children":[],"text_value":None,
            "engine":None,"error":None,"scope":None,"scope_safe":False,"window":0}
    if win32gui is None:return report
    try:
        import win32process
        from doubao_typeless.platform.windows.focus import automation,focused_chain,runtime_id,classify_element
        hwnd=int(win32gui.GetForegroundWindow() or 0)
        report["window"]=hwnd
        if not hwnd:return report
        pid=int(win32process.GetWindowThreadProcessId(hwnd)[1])
        if anchor and (anchor.get("window")!=hwnd or (anchor.get("scope") or {}).get("pid")!=pid):
            return report
        with automation() as uia:
            focused=uia.GetFocusedElement()
            if not focused or int(focused.CurrentProcessId)!=pid:return report
            chain=focused_chain(uia,focused,limit=12)
            focus_id={"runtime_id":list(runtime_id(focused)),"pid":pid}
            report.update(engine="IUIAutomation",focus=focus_id)
            if anchor:
                scope=anchor.get("scope") or {}
                scope_id=tuple(scope.get("runtime_id") or [])
                if not scope_id:return report
                # 用户转到容器外时，不再查询或把焦点拉回来。
                container=next((node for node,_ in chain if runtime_id(node)==scope_id),None)
                if container is None:return report
                report["composer_control"]=anchor.get("composer_control")
            else:
                if classify_element([d for _,d in chain])!="composer":return report
                report["composer_control"]=focus_id
                container=None
                for node,desc in chain[1:7]:
                    identity=f"{desc['automation_id']} {desc['class_name']}".lower()
                    label=str(desc.get("name") or "").strip().lower()
                    semantic_group=(desc.get("control_type") in {50026,50033} and label in
                                    {"composer","message composer","chat composer","消息编辑器","对话输入区"})
                    if semantic_group or any(k in identity for k in ("composer","chatinput","chat-input","promptinput","prompt-form")):
                        container=node;break
                # 有些聊天应用没有命名容器；只在最近完整、唯一输入区按结构建立锚点。
                # 后续采样必须仍在这个确切容器内，不能临时换成别的聊天框。
                if container is None:
                    from doubao_typeless.adapters.composer_scope import find_structural_scope
                    container = find_structural_scope(uia, chain)
                if container is None:return report
                scope_id=runtime_id(container)
                if not scope_id:return report
                scope={"runtime_id":list(scope_id),"pid":pid}
            report["scope"]=scope;report["scope_safe"]=True
            report["image_children"]=_collect_image_children(uia,container)
            return report
    except Exception as exc:
        report["error"]=type(exc).__name__
        return report


def probe_uia(anchor=None) -> dict:
    if win32gui is None:return {"composer_control":None,"image_children":[]}
    from doubao_typeless.platform.windows.automation_host import host
    return host().call("attachments",{"anchor":anchor} if anchor else {})


def _collect_image_children(uia, element, *, depth=0, found=None, budget=None):
    found=found if found is not None else []
    budget=budget if budget is not None else [0,time.monotonic()+.4]
    budget[0]+=1
    if depth>8 or len(found)>=16 or budget[0]>256 or time.monotonic()>budget[1]:return found
    try:
        ctl=str(getattr(element,"CurrentControlType","") or "")
        name=str(getattr(element,"CurrentName","") or "")
        cls=str(getattr(element,"CurrentClassName","") or "")
        blob=f"{name} {cls}".lower()
        from doubao_typeless.adapters.composer_scope import attachment_remove
        identity=str(getattr(element,"CurrentAutomationId","") or "")
        if ctl=="50006" or (ctl=="50000" and attachment_remove(name, identity)):
            try:rid=list(element.GetRuntimeId())
            except Exception:rid=[]
            found.append({"control_type":ctl,"runtime_id":rid,
                          "pending":any(x in blob for x in ("uploading","loading","failed","上传中","失败","处理中"))})
    except Exception:pass
    try:
        walker=uia.ControlViewWalker;child=walker.GetFirstChildElement(element)
        while child and len(found)<16 and budget[0]<256 and time.monotonic()<=budget[1]:
            _collect_image_children(uia,child,depth=depth+1,found=found,budget=budget)
            child=walker.GetNextSiblingElement(child)
    except Exception:pass
    return found


def capture_image_baseline(anchor=None) -> dict:
    # 默认调用保留旧的可测试入口；后续采样绑定同一容器。
    report=probe_uia(anchor) if anchor else probe_uia()
    if win32gui is not None:report["window"]=int(win32gui.GetForegroundWindow() or 0)
    return report


def same_composer_scope(baseline, report):
    if not baseline or not report:return False
    if report.get("window")!=baseline.get("window"):return False
    if baseline.get("scope"):
        return (report.get("scope_safe") is True and report.get("scope")==baseline["scope"]
                and report.get("composer_control")==baseline.get("composer_control"))
    # 兼容旧探针：仍要求精确焦点；不把缺容器证据升级成更宽松策略。
    return report.get("focus")==baseline.get("focus")


def observe_image(baseline=None, *, timeout_s=0.25, cancelled=None) -> str:
    if not baseline or not baseline.get("composer_control"):return "unknown"
    previous={tuple(n["runtime_id"]) for n in baseline.get("image_children") or [] if n.get("runtime_id")}
    deadline=time.monotonic()+max(0,min(timeout_s,8));stable=None
    while True:
        if cancelled and cancelled():return "unknown"
        report=capture_image_baseline(baseline) if baseline.get("scope") else capture_image_baseline()
        if not same_composer_scope(baseline,report):return "unknown"
        candidates={tuple(n["runtime_id"]) for n in report.get("image_children") or []
                    if n.get("runtime_id") and n.get("control_type") in {"50006", "50000"} and not n.get("pending")}
        added=candidates-previous
        if added and added==stable and len(candidates)>len(previous):return "observed"
        stable=added
        if time.monotonic()>=deadline:return "unknown"
        time.sleep(.1)


def resume_composer_direct(anchor, expected):
    """图片自动聚焦附件后，只恢复原容器内的原输入控件；不按文字或坐标猜。"""
    from doubao_typeless.platform.windows.focus import automation,runtime_id,_read_target_direct
    if win32gui is None or not anchor or len(expected)<7:return None
    report=_probe_uia_direct(anchor)
    if not same_composer_scope(anchor,report):return None
    with automation() as uia:
        focused=uia.GetFocusedElement()
        from doubao_typeless.platform.windows.focus import focused_chain
        chain=focused_chain(uia,focused,limit=12)
        scope_id=tuple(anchor["scope"]["runtime_id"])
        container=next((node for node,_ in chain if runtime_id(node)==scope_id),None)
        if container is None:return None
        node=_element_by_id(uia,container,expected[5])
        if node is None:return None
        node.SetFocus()
    actual=_read_target_direct()
    return list(actual) if tuple(actual.runtime_id)==tuple(expected[5]) and actual.kind=="composer" else None


def observe_text() -> str:
    report = probe_uia()
    if not report.get("composer_control"):
        return "unknown"
    if report.get("text_value"):
        return "observed"
    return "unknown"
