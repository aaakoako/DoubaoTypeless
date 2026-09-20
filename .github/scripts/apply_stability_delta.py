"""One exact authorized source patch; never writes a workflow, main or release.
Checks both parent and payload, removes only its own transport and commits normally.
"""
from __future__ import annotations
import base64, hashlib, lzma, os
from pathlib import Path
import subprocess, tempfile

BRANCH = 'v3/assistant-runtime-safety'
BASE = '441769324e35d49a96b97908544acfa0096d61d6'
HASH = '44f114414df2bb98428e0f13865ba236e37013d4e8275db4baa7a6374509991f'
FILES = '''docs/v3-delivery/CHECKPOINT.json
src/doubao_typeless/adapters/cursor_windows.py
src/doubao_typeless/app.py
src/doubao_typeless/core/attempt.py
src/doubao_typeless/platform/windows/automation_host.py
src/doubao_typeless/platform/windows/focus.py
src/doubao_typeless/platform/windows/guards.py
src/doubao_typeless/platform/windows/integrity.py
src/doubao_typeless/platform/windows/native_input.py
src/doubao_typeless/services/delivery.py
src/doubao_typeless/services/v3_diagnostics.py
src/doubao_typeless/ui/desktop.py
src/doubao_typeless/ui/hud.py
src/doubao_typeless/ui/insert_status.py
tests/test_v3_stability_contract.py
tests/test_v3_stability_hud.py
tools/run_v3.py
tools/verify_candidate_browser.py'''.splitlines()

def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def main():
    if os.environ.get('GITHUB_REF') != 'refs/heads/' + BRANCH:
        raise RuntimeError('wrong branch')
    parent = run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()
    if parent != BASE:
        raise RuntimeError('unexpected parent; reconcile rather than overwrite')
    paths = sorted(Path('.stability-delta').glob('chunk-*.txt'))
    if [p.name for p in paths] != ['chunk-00.txt','chunk-01.txt']:
        raise ValueError('unexpected chunks')
    encoded = ''.join(p.read_text(encoding='utf-8').strip() for p in paths)
    if len(encoded) != 28440:
        raise ValueError('wrong encoded length')
    patch = lzma.decompress(base64.b64decode(encoded,validate=True),memlimit=128*1024*1024)
    if len(patch) != 77068 or hashlib.sha256(patch).hexdigest() != HASH:
        raise ValueError('wrong source digest')
    with tempfile.NamedTemporaryFile(suffix='.patch') as fh:
        fh.write(patch);fh.flush()
        listing=run('git','apply','--numstat',fh.name,capture_output=True,text=True).stdout
        actual=[line.split('\t',2)[2] for line in listing.splitlines()]
        if sorted(actual)!=sorted(FILES):
            raise ValueError('source file list mismatch')
        for name in actual:
            if name.startswith(('/','.git/','.github/')) or '..' in Path(name).parts:
                raise ValueError('unsafe source path')
        run('git','apply','--check','--index',fh.name)
        run('git','apply','--index',fh.name)
    run('git','rm','-r','.stability-delta')
    run('git','rm','.github/scripts/apply_stability_delta.py')
    run('git','config','user.name','github-actions[bot]')
    run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    run('git','commit','-m','fix(v3): isolate native target inspection and preserve actionable insertion feedback')
    run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
    print('Imported source; downstream jobs must validate this exact HEAD.')

if __name__=='__main__':
    main()
