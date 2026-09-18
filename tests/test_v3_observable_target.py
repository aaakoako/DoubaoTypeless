"""Product observer without GUI."""
from __future__ import annotations

import json

from doubao_typeless.adapters.observable_target import FileTargetObserver


def test_file_observer_sees_new_image(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"images": [], "text": "BEFORE\n"}), encoding="utf-8")
    observer = FileTargetObserver(path)
    path.write_text(
        json.dumps({"images": [{"sha256": "abc"}], "text": "BEFORE\nhello\n"}),
        encoding="utf-8",
    )
    assert observer.observe_image() == "observed"
    assert observer.observe_text() == "observed"
