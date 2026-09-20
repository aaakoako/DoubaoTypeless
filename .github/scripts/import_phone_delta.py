"""One exact, hash-checked patch transport for the authorized assistant branch.
This temporary importer removes itself/payload and restores read-only candidate CI.
No force push, tags, Release, main/base-branch writes or external source downloads.
"""
from __future__ import annotations
import base64, hashlib, json, lzma, os
from pathlib import Path
import subprocess, tempfile

BRANCH='v3/assistant-runtime-safety'
BASE='dc517b5b221d36213a572b7f33084d34cf164891'
DIGEST='90ff0fafeadee1caac6be760cbe1b287cbd6cb06e8a116083bead2fe1f94b7fb'
WORKFLOW='beee66b667c8772e63212e90866720903f53916c303e4f8d8ced05f10c96726a'
SIZE=147286

def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)

def main():
    if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('wrong branch')
    parent=run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()
    if parent!=BASE:raise RuntimeError('unexpected transport parent')
    folder=Path('.assistant-phone-delta');manifest=json.loads((folder/'manifest.json').read_text())
    chunks=sorted(folder.glob('chunk-*.txt'))
    if [p.name for p in chunks]!=[f'chunk-{i:02}.txt'for i in range(6)]:raise ValueError('chunks')
    data=base64.b64decode(''.join(p.read_text().strip() for p in chunks),validate=True)
    patch=lzma.decompress(data,memlimit=256*1024*1024)
    if len(patch)!=SIZE or hashlib.sha256(patch).hexdigest()!=DIGEST:raise ValueError('patch integrity')
    workflow=(folder/'workflow.yml').read_bytes()
    if hashlib.sha256(workflow).hexdigest()!=WORKFLOW:raise ValueError('workflow integrity')
    with tempfile.NamedTemporaryFile(suffix='.patch') as fh:
        fh.write(patch);fh.flush()
        listing=run('git','apply','--numstat',fh.name,capture_output=True,text=True).stdout
        files=[line.split('\t',2)[2]for line in listing.splitlines()]
        if sorted(files)!=sorted(manifest['files']):raise ValueError('file list')
        for name in files:
            if name.startswith(('/','.git/','.github/')) or '..' in Path(name).parts:raise ValueError('unsafe path')
        run('git','apply','--check','--index',fh.name)
        run('git','apply','--index',fh.name)
    run('python','-m','pip','install','Pillow')
    run('python','tools/export_v3_icon.py')
    run('npm','ci',cwd='web');run('npm','run','typecheck',cwd='web');run('npm','run','build',cwd='web')
    Path('.github/workflows/assistant-candidate.yml').write_bytes(workflow)
    run('git','add','-A','--','assets','web/public','web/dist','.github/workflows/assistant-candidate.yml')
    run('git','rm','-r','.assistant-phone-delta')
    run('git','rm','.github/scripts/import_phone_delta.py')
    run('git','config','user.name','github-actions[bot]')
    run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    run('git','commit','-m','feat(v3): make phone drafts authoritative, resume weak-network image uploads and refresh native HUD')
    run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
    print('Source import complete; candidate jobs must test this exact new HEAD.')

if __name__=='__main__':main()
