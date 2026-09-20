"""Exact source-only transfer for the authorized isolated branch; never changes workflows."""
from pathlib import Path
import base64, hashlib, json, lzma, os, subprocess, tempfile
BRANCH='v3/assistant-runtime-safety'
BASE='30421e3cb306402ef2a67ca54b6e8824f9f2630d'
SHA='021e829fe66be6f18cfcb0219fea6fe04f21addd6f7cfe3ce1d861de6e8586b4'
def run(*args,**kw): return subprocess.run(args,check=True,**kw)
def main():
    if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH: raise RuntimeError('wrong branch')
    if run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()!=BASE: raise RuntimeError('unexpected base')
    folder=Path('.assistant-unified'); manifest=json.loads((folder/'manifest.json').read_text())
    chunks=sorted(folder.glob('chunk-*.txt'))
    if [p.name for p in chunks]!=[f'chunk-{i:02}.txt' for i in range(6)]:raise ValueError('chunk list')
    data=base64.b64decode(''.join(p.read_text().strip() for p in chunks),validate=True)
    patch=lzma.decompress(data,memlimit=256*1024*1024)
    if len(patch)!=131215 or hashlib.sha256(patch).hexdigest()!=SHA:raise ValueError('integrity')
    with tempfile.NamedTemporaryFile(suffix='.patch') as f:
        f.write(patch);f.flush()
        names=[s.split('\t',2)[2] for s in run('git','apply','--numstat',f.name,capture_output=True,text=True).stdout.splitlines()]
        if sorted(names)!=sorted(manifest['files']):raise ValueError('file allowlist')
        for name in names:
            if name.startswith(('/','.git/','.github/')) or '..' in Path(name).parts:raise ValueError('unsafe path')
        run('git','apply','--check','--index',f.name);run('git','apply','--index',f.name)
    run('python','-m','pip','install','Pillow')
    run('python','tools/export_ui_theme.py','--check');run('python','tools/export_v3_icon.py')
    run('npm','ci',cwd='web');run('npm','run','typecheck',cwd='web');run('npm','run','build',cwd='web')
    run('git','add','-A','--','assets','web/public','web/dist')
    run('git','rm','-r','.assistant-unified');run('git','rm','tools/import_unified_delta.py')
    run('git','config','user.name','github-actions[bot]')
    run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    run('git','commit','-m','feat(v3): unify Mist Indigo interfaces and safely complete mixed image-text delivery')
    run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
if __name__=='__main__':main()
