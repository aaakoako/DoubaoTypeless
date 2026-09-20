"""语义容器候选及附件类型边界；不把旧附件当作新增附件。"""
import pytest
from doubao_typeless.adapters.composer_scope import valid_scope,attachment_remove,role_for_button
from doubao_typeless.adapters import cursor_windows as adapter

def records():return [
 {'control_type':50004,'enabled':True,'runtime_id':[1,2]},
 {'control_type':50000,'name':'Add photos and files'},
 {'control_type':50000,'name':'Use voice mode'}]

def test_single_editor_and_toolbar_are_required():
    assert valid_scope(records(),[1,2],complete=True)
    assert not valid_scope(records(),[1,2],complete=False)
    assert not valid_scope(records()[:-1],[1,2],complete=True)
    assert not valid_scope(records()+[{'control_type':50004,'enabled':True,'runtime_id':[3]}],[1,2],complete=True)

@pytest.mark.parametrize('name',['移除图片','Remove attachment','Delete file'])
def test_remove_attachment_controls_are_counted(name):assert attachment_remove(name)

@pytest.mark.parametrize('name',['Delete conversation','Remove message','删除会话','删除'])
def test_delete_conversation_is_never_attachment(name):assert not attachment_remove(name)


def test_old_images_recreated_without_growth_do_not_confirm_new_image(monkeypatch):
    b={'window':1,'composer_control':{'runtime_id':[2]},'focus':2,'image_children':[{'runtime_id':[10]}]}
    report={**b,'image_children':[{'runtime_id':[11],'control_type':'50006','pending':False}]}
    monkeypatch.setattr(adapter,'capture_image_baseline',lambda *args:report)
    assert adapter.observe_image(b,timeout_s=0)=='unknown'


def test_new_remove_attachment_can_confirm_without_exposed_image(monkeypatch):
    b={'window':1,'composer_control':{'runtime_id':[2]},'focus':2,'image_children':[]}
    report={**b,'image_children':[{'runtime_id':[11],'control_type':'50000','pending':False}]}
    monkeypatch.setattr(adapter,'capture_image_baseline',lambda *args:report)
    assert adapter.observe_image(b,timeout_s=.2)=='observed'
