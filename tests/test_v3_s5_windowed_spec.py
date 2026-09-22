from pathlib import Path


def test_windowed_spec_is_separately_named():
    root = Path(__file__).resolve().parents[1] / "packaging"
    console = (root / "v3_preview.spec").read_text(encoding="utf-8")
    windowed = (root / "v3_preview_windowed.spec").read_text(encoding="utf-8")
    assert 'name="DoubaoTypelessV3Preview"' in console
    assert "console=True" in console
    from types import SimpleNamespace
    calls=[]
    def executable(*args, **kwargs):
        calls.append(kwargs)
        return None
    namespace={'SPECPATH':str(root), 'Analysis':lambda *a,**k:SimpleNamespace(
        binaries=[],pure=[],zipped_data=[],scripts=[],zipfiles=[],datas=[]),
        'PYZ':lambda *a,**k:None, 'EXE':executable,'COLLECT':executable}
    exec(compile(windowed,str(root/'v3_preview_windowed.spec'),'exec'),namespace)
    assert calls[0]['name']=='DoubaoTypelessV3PreviewUI' and calls[0]['console'] is False
    assert calls[1]['name']=='DoubaoTypelessV3PreviewUI'
    assert 'name="DoubaoTypelessV3PreviewUI"' not in console
