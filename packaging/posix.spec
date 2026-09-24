"""Native macOS/Linux builds; run on the target OS and CPU architecture."""
from pathlib import Path
import json
import sys

ROOT = Path(SPECPATH).resolve().parent
info = json.loads((ROOT / 'build-info.json').read_text())
assert len(info['source_sha']) == 40
assert (ROOT / 'web/dist/index.html').is_file()
assert sys.platform in {'darwin', 'linux'}
sys.path.insert(0, str(ROOT / 'tools'))
from collect_runtime_notices import collect, qt_binary_allowed

hidden = ['qrcode.image.pil']
if sys.platform == 'darwin':
    hidden += ['pynput.keyboard._darwin', 'pynput.mouse._darwin', 'ApplicationServices',
               'Quartz', 'AppKit', 'keyring.backends.macOS']
else:
    hidden += ['pynput.keyboard._xorg', 'pynput.mouse._xorg', 'Xlib.ext.xtest',
               'keyring.backends.SecretService']
a = Analysis([str(ROOT / 'tools/run_v3.py')], pathex=[str(ROOT / 'src')],
    datas=[(str(ROOT / 'web/dist'), 'web/dist'), (str(ROOT / 'assets'), 'assets'),
           (str(ROOT / 'src/doubao_typeless/static'), 'doubao_typeless/static'),
           (str(ROOT / 'LICENSE'), '.'), (str(ROOT / 'build-info.json'), '.'),
           (str(ROOT / 'docs/release/CROSS_PLATFORM.md'), 'docs/release')],
    hiddenimports=hidden, excludes=['customtkinter', 'comtypes', 'win32api', 'win32gui'])
a.binaries = [entry for entry in a.binaries if qt_binary_allowed(entry[0])]
# Analysis also puts SONAME symlinks in datas; filter them with their libraries.
a.datas = [entry for entry in a.datas if qt_binary_allowed(entry[0])]
a.datas += collect([entry[0] for entry in a.pure], [entry[0] for entry in a.binaries],
                   ROOT, ROOT / 'build/runtime-notices', native_binaries=a.binaries)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PocketComposer',
          console=sys.platform != 'darwin', strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='PocketComposer', strip=False, upx=False)
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='Pocket Composer.app', icon=str(ROOT / 'build/icon.icns'),
                 bundle_identifier='io.github.aaakoako.pocketcomposer', version=info['version'],
                 info_plist={'CFBundleDisplayName': 'Pocket Composer',
                             'NSHighResolutionCapable': True,
                             'NSAccessibilityUsageDescription': 'Paste your phone draft into the input field you selected.',
                             'NSScreenCaptureUsageDescription': 'Capture a screen area you request and send it to your paired phone.'})
