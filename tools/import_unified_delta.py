"""Exact three-file follow-up; no workflow mutations or test exclusions."""
from pathlib import Path
import hashlib,os,subprocess
BRANCH='v3/assistant-runtime-safety'
def run(*args,**kw):return subprocess.run(args,check=True,**kw)
def main():
    if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('wrong branch')
    if run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()!='b0aad5d8279161dacb4822e7217c456363efdeda':raise RuntimeError('wrong parent')
    p=Path('.assistant-unified-followup.patch')
    if hashlib.sha256(p.read_bytes()).hexdigest()!='86531ff60655a87451a782a322bc06294d0ee9153ac6e2df0ff90c2fb4654aff':raise ValueError('integrity')
    files=[s.split('\t',2)[2] for s in run('git','apply','--numstat',str(p),capture_output=True,text=True).stdout.splitlines()]
    if sorted(files)!=sorted(['src/doubao_typeless/app.py','tests/test_v3_unified_composer.py','tools/verify_candidate_browser.py']):raise ValueError('allowlist')
    run('git','apply','--check','--index',str(p));run('git','apply','--index',str(p))
    run('git','rm',str(p),'tools/import_unified_delta.py')
    run('git','config','user.name','github-actions[bot]');run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    run('git','commit','-m','fix(v3): preserve native paste completion and cover the production input-stamp wrapper')
    run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
if __name__=='__main__':main()
