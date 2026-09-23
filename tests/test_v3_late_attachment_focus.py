"""An upload may move focus after the immediate image-paste recovery."""
import pytest
from doubao_typeless.core.attempt import Attempt
from doubao_typeless.platform.windows.focus import FocusSnapshot
from doubao_typeless.services.delivery import DeliveryService

TARGET=FocusSnapshot('Chrome_WidgetWin_1','Chat',10,20,30,(40,50),'composer')
ATTACHMENT=TARGET._replace(runtime_id=(60,),kind='unknown')

@pytest.mark.parametrize('boundary',['next_image','image_clipboard','text','text_clipboard'])
@pytest.mark.parametrize('user_switched',[False,True])
def test_late_attachment_focus_only_resumes_with_native_guard(boundary,user_switched):
    current=[TARGET];pasted=[];clip=[];recoveries=[]
    def progress(event):
        if ((boundary=='next_image' and event['stage']=='image' and event['index']==2)
                or (boundary=='text' and event['stage']=='text')):
            current[0]=ATTACHMENT
    def image(_):
        clip[:]=['image']
        if boundary=='image_clipboard' and len(pasted)==1:current[0]=ATTACHMENT
    def text(_):
        clip[:]=['text']
        if boundary=='text_clipboard':current[0]=ATTACHMENT
    def resume(expected):
        if current[0]!=TARGET:
            recoveries.append(expected)
            if user_switched:return None
            current[0]=TARGET
        return current[0]
    service=DeliveryService(read_focus=lambda:current[0],paste=lambda:pasted.append(clip[0]),
        set_clipboard_image=image,set_clipboard_text=text,observe_image=lambda:'unknown',
        resume_input=resume,progress=progress)
    attempt=service.run(Attempt('a','i','b','x'),{'assets':[{'asset_id':'1'},{'asset_id':'2'}],'text':'body'})
    assert recoveries==[TARGET]
    if user_switched:
        assert attempt.error_code=='TARGET_CHANGED' and 'text' not in pasted
    else:
        assert not attempt.error_code and pasted==['image','image','text']
