from pathlib import Path


def test_windowed_spec_is_separately_named():
    root = Path(__file__).resolve().parents[1] / "packaging"
    console = (root / "v3_preview.spec").read_text(encoding="utf-8")
    windowed = (root / "v3_preview_windowed.spec").read_text(encoding="utf-8")
    assert 'name="DoubaoTypelessV3Preview"' in console
    assert "console=True" in console
    assert 'name="DoubaoTypelessV3PreviewUI"' in windowed
    assert "console=False" in windowed
    assert 'name="DoubaoTypelessV3PreviewUI"' not in console
