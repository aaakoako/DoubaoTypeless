from doubao_typeless.platform.windows.focus import classify_element
from doubao_typeless.platform.windows.composer_locator import composer_candidate


def test_observed_codex_label_survives_conversation_title_but_rejects_terminal_and_password():
    item={'control_type':50004,'enabled':True,'readonly':False,'name':'随心输入'}
    assert composer_candidate([item])
    assert classify_element([item,{'control_type':50030,'name':'修复 PowerShell terminal 命令'}])=='composer'
    assert classify_element([item,{'class_name':'xterm terminal'}])=='terminal'
    assert not composer_candidate([{**item,'password':True}])
    assert not composer_candidate([{**item,'class_name':'monaco-editor'}])
