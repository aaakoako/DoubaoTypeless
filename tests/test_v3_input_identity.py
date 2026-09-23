"""控件级投递和手动确认的组件测试；不替代真实Cursor/Windows验证。"""
import copy
import pytest
from doubao_typeless.platform.windows.focus import FocusSnapshot, classify_element, same_target
from doubao_typeless.core.policy import may_inject
from doubao_typeless.core.attempt import Attempt
from doubao_typeless.services.delivery import DeliveryService


def descriptor(**kw):
    return dict(control_type=50004, enabled=True, name="", automation_id="", class_name="Edit", **kw)


def test_password_never_allowed():
    assert classify_element([descriptor(password=True)]) == "password"
    assert not may_inject("password", wants_images=False)


def test_editable_code_is_not_chat():
    assert classify_element([descriptor(), {"class_name":"monaco-editor"}]) == "code"


def test_chat_must_be_editable_not_a_title():
    assert classify_element([{"control_type":50020,"name":"ChatInput","enabled":True}]) == "unknown"
    d=descriptor(); d["name"]="Ask anything"
    assert classify_element([d])=="composer"


def test_remote_plain_edit_but_not_unknown():
    assert may_inject("edit", wants_images=False, remote=True)
    assert not may_inject("edit", wants_images=True, remote=True)
    assert not may_inject("unknown", wants_images=False, remote=True)


def test_two_controls_in_same_window_are_distinct():
    a=FocusSnapshot("Chrome_WidgetWin_1","Cursor",42,7,0,(3,4),"composer")
    b=a._replace(runtime_id=(3,5))
    assert not same_target(a,b)
    assert same_target(a,copy.deepcopy(a))


def test_switch_control_during_modifier_wait_stops():
    a=FocusSnapshot("Chrome_WidgetWin_1","Cursor",42,7,0,(3,4),"composer")
    focus=[a]; pasted=[]
    def wait():
        focus[0]=a._replace(runtime_id=(3,8),kind="code")
        return True
    delivery=DeliveryService(paste=lambda:pasted.append(True),set_clipboard_image=lambda _:None,
        set_clipboard_text=lambda _:None,read_focus=lambda:focus[0],wait_modifiers=wait)
    result=delivery.run(Attempt("a","i","b","generic"),{"text":"test","assets":[]})
    assert result.error_code=="TARGET_CHANGED" and pasted==[]


def test_manual_image_confirmation_skips_only_confirmed_images(tmp_path):
    from doubao_typeless.app import V3App
    from doubao_typeless.core.bundle import freeze_bundle
    from doubao_typeless.core.attempt import Step
    from tests.test_v3_s1_commands import _stub_delivery
    app=V3App(data_dir=tmp_path,port=0)
    pasted=[]; _stub_delivery(app,pasted)
    app.draft.text="说明"
    app.draft.assets=[{"asset_id":"A","bytes":1,"status":"ready"},{"asset_id":"B","bytes":1,"status":"ready"}]
    bundle=freeze_bundle(app.draft,bundle_id="b")
    app.bridge.last_bundle=bundle
    app._last_attempt=Attempt("a","i","b","generic",result="UNKNOWN",steps=[Step(0,"image","A","unknown","none")])
    app._last_target_fp=tuple(app._read_focus())
    app._hydrate_bundle=lambda b: {**b,"assets":[{**a,"bytes_data":b"image"} for a in b["assets"]]}
    images=[]; app.delivery._set_image=lambda data:images.append(data)
    app.delivery._observe_image=lambda:"observed"
    out=app.confirm_recovery("confirm_continue")
    assert len(images)==1
    assert out["steps"][0]["asset_id"]=="A"
    assert out["steps"][0]["evidence"]=="user_confirmed"
    assert len(out["steps"])==3


def test_confirmation_cannot_continue_into_other_target(tmp_path):
    from doubao_typeless.app import V3App
    from doubao_typeless.core.attempt import Step
    app=V3App(data_dir=tmp_path,port=0)
    app.bridge.last_bundle={"bundle_id":"b"}
    app._last_attempt=Attempt("a","i","b","generic",result="UNKNOWN",steps=[Step(0,"image","A","unknown","none")])
    app._last_target_fp=("x","old",1)
    app._read_focus=lambda:("x","new",2)
    assert app.confirm_recovery("confirm_continue")["error_code"]=="TARGET_CHANGED"


def test_readonly_edit_rejects_paste():
    kind = classify_element([descriptor(readonly=True, value_available=True)])
    assert kind == "readonly"
    assert not may_inject(kind, wants_images=False)
    assert not may_inject(kind, wants_images=False, remote=True)


def test_repository_title_does_not_mean_our_window():
    from doubao_typeless.core.policy import is_own_window
    assert not is_own_window("Chrome_WidgetWin_1", "DoubaoTypeless — Cursor")
    assert not is_own_window("Chrome_WidgetWin_1", "DoubaoTypeless GitHub — Chrome")
    assert is_own_window("Qt611QWindowIcon", "DoubaoTypeless V3 · 体验版")
    assert is_own_window("Qt611QWindowIcon", "查看图片")


def test_readonly_comes_from_actual_uia_property_reader():
    from doubao_typeless.platform.windows.focus import describe
    class ReadOnlyControl:
        CurrentControlType = 50004
        CurrentIsEnabled = True
        CurrentName = "ChatInput"
        def GetCurrentPropertyValue(self, key):
            return key in {30043, 30046}
    desc = describe(ReadOnlyControl())
    assert desc["readonly"] is True
    assert classify_element([desc]) == "readonly"
