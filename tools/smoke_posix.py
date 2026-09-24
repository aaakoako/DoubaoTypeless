"""Frozen startup/HTTP/IPC shutdown; no key injection or user data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid


def main():
    executable = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix='pocket-smoke-') as temp:
        data = Path(temp)
        env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'DT_V3_DISABLE_HOTKEYS': '1',
               'DT_V3_DATA_DIR': temp, 'DT_V3_PIPE': 'PocketSmoke-' + uuid.uuid4().hex}
        with (data / 'process.log').open('wb') as log:
            child = subprocess.Popen([executable, '--minimized'], env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline and child.poll() is None:
                    pair = data / 'pair.txt'
                    if pair.exists():
                        url = pair.read_text().splitlines()[0]
                        port = url.split(':')[-1].strip('/')
                        try:
                            with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1) as response:
                                if response.status == 200:
                                    break
                        except OSError:
                            pass
                    time.sleep(.2)
                else:
                    raise RuntimeError('Frozen HTTP startup failed')
                stop = subprocess.run([executable, '--quit'], env=env, timeout=20, capture_output=True)
                if stop.returncode or child.wait(timeout=30) != 0:
                    raise RuntimeError('Frozen IPC shutdown failed')
                print(json.dumps({'frozen_startup': True, 'http': True, 'ipc_shutdown': True,
                                  'native_insertion_tested': False}))
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
                print((data / 'process.log').read_text(errors='replace'))


if __name__ == '__main__':
    main()
