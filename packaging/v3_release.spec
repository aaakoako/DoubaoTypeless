from pathlib import Path
import json
root = Path(SPECPATH).resolve().parent
info = json.loads((root / 'build-info.json').read_text(encoding='utf-8'))
assert info['channel'] in ('release-candidate', 'stable'), 'Generate release identity first'
assert len(info['source_sha']) == 40
assert (root / 'web/dist/index.html').is_file(), 'Build production frontend first'
APP_NAME = 'DoubaoTypeless'
VERSION_FILE = str(root/'build/v3-version.txt')
exec(compile((root / 'packaging/v3_preview_windowed.spec').read_text(encoding='utf-8'), 'v3_preview_windowed.spec', 'exec'))
