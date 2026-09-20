"""Apply one reviewed, hash-checked source delta on the isolated assistant branch.
No arbitrary remote downloads, no force push, no tags/releases/main writes.
The payload is removed from the resulting source commit; it is transport only.
"""
from __future__ import annotations
import base64
import hashlib
import json
import lzma
import os
from pathlib import Path
import subprocess
import tempfile

BRANCH = 'v3/assistant-runtime-safety'
EXPECTED_BASE = 'e59dfce656bb25bd70607863f28eda82622feef7'
EXPECTED_HASH = '4ce57d00b4ed071ae978dc2e5a9dd3c96dc8f889d7c253109dbaef8da0206d10'

def run(*args: str, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def main():
    if os.environ.get('GITHUB_REF') != 'refs/heads/' + BRANCH:
        raise RuntimeError('Source import is restricted to the isolated assistant branch')
    folder = Path('.assistant-delivery')
    if folder.exists():
        manifest = json.loads((folder / 'manifest.json').read_text())
        if manifest['base_commit'] != EXPECTED_BASE or manifest['sha256'] != EXPECTED_HASH:
            raise ValueError('unexpected manifest')
        chunks = sorted(folder.glob('chunk-*.txt'))
        if [p.name for p in chunks] != [f'chunk-{i:02d}.txt' for i in range(10)]:
            raise ValueError('missing or unexpected source chunks')
        packed = base64.b64decode(''.join(p.read_text().strip() for p in chunks), validate=True)
        patch = lzma.decompress(packed, memlimit=256*1024*1024)
        if len(patch) != 240582 or hashlib.sha256(patch).hexdigest() != EXPECTED_HASH:
            raise ValueError('source delta hash mismatch')
        with tempfile.NamedTemporaryFile(suffix='.patch') as fh:
            fh.write(patch); fh.flush()
            output = run('git','apply','--numstat',fh.name,capture_output=True,text=True).stdout
            files = [line.split('\t',2)[2] for line in output.splitlines()]
            if sorted(files) != sorted(manifest['files']):
                raise ValueError('source delta file list mismatch')
            for path in files:
                if path.startswith(('/', '.github/', '.git/')) or '..' in Path(path).parts:
                    raise ValueError('unsafe source path')
            run('git','apply','--check','--index',fh.name)
            run('git','apply','--index',fh.name)
        # Compile the actual imported phone frontend rather than ship stale dist.
        run('npm','ci',cwd='web')
        run('npm','run','typecheck',cwd='web')
        run('npm','run','build',cwd='web')
        run('git','add','-A','web/dist')
        run('git','rm','-r','.assistant-delivery')
        run('git','config','user.name','github-actions[bot]')
        run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
        run('git','commit','-m','feat(v3): integrate complete text/image workflow, native review and safe recovery')
        # A concurrent branch update is rejected by normal Git non-fast-forward rules.
        run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
    sha = run('git','rev-parse','HEAD',capture_output=True,text=True).stdout.strip()
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as fh:
        fh.write(f'source_sha={sha}\n')
    print('Validated source commit:',sha)

if __name__ == '__main__':
    main()
