"""One exact source-only follow-up, no workflow/main/tag/Release mutations."""
from pathlib import Path
import base64,hashlib,lzma,os,subprocess,tempfile
BRANCH='v3/assistant-runtime-safety'
BASE='9dba9e582fd8d9722e70e43a1f67aee9a10573f3'
HASH='3e6b7c4ed1df4bccdedcfe4b210cfc68fc74e7abfc6182f45621c0d5b313ba70'
FILES=['src/doubao_typeless/app.py','src/doubao_typeless/ui/hud.py','src/doubao_typeless/ui/insert_status.py','tests/test_v3_stability_contract.py','tests/test_v3_stability_hud.py','tools/verify_candidate_browser.py']
def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def main():
    if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('wrong branch')
    if run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()!=BASE:raise RuntimeError('unexpected parent')
    encoded=Path('.stability-followup.b64').read_text(encoding='utf-8').strip()
    if len(encoded)!=5036:raise ValueError('payload length')
    patch=lzma.decompress(base64.b64decode(encoded,validate=True),memlimit=128*1024*1024)
    if len(patch)!=9320 or hashlib.sha256(patch).hexdigest()!=HASH:raise ValueError('payload digest')
    with tempfile.NamedTemporaryFile(suffix='.patch') as fh:
        fh.write(patch);fh.flush()
        listing=run('git','apply','--numstat',fh.name,capture_output=True,text=True).stdout
        if sorted(line.split('\t',2)[2]for line in listing.splitlines())!=sorted(FILES):raise ValueError('file list')
        run('git','apply','--check','--index',fh.name);run('git','apply','--index',fh.name)
    run('git','rm','.stability-followup.b64','.github/scripts/apply_stability_followup.py')
    run('git','config','user.name','github-actions[bot]')
    run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    run('git','commit','-m','fix(v3): finish duplicate requests visibly and verify raw browser paste content')
    run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
if __name__=='__main__':main()
