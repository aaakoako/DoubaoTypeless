"""Apply one exact source delta, then remove transport; never modify workflows."""
import hashlib,os,subprocess
from pathlib import Path
BRANCH='v3/assistant-runtime-safety'
BASE='c121790da60e75a7009ead57f1244877e6e5390a'
DIGEST='15c0bb65991e42cd3107b25fb60d9060755f6a56396fc0ef5240f313011add25'
FILES={'src/doubao_typeless/app.py','src/doubao_typeless/ui/desktop.py','src/doubao_typeless/ui/hud.py','tools/verify_candidate_browser.py'}
def run(*a,**kw):return subprocess.run(a,check=True,**kw)
def main():
 if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('wrong branch')
 if run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()!=BASE:raise RuntimeError('wrong parent')
 path=Path('.github/scripts/modal_delta.patch')
 if hashlib.sha256(path.read_bytes()).hexdigest()!=DIGEST:raise RuntimeError('wrong patch')
 listing=run('git','apply','--numstat',str(path),capture_output=True,text=True).stdout
 if {x.split('\t',2)[2]for x in listing.splitlines()}!=FILES:raise RuntimeError('wrong files')
 run('git','apply','--check','--index',str(path));run('git','apply','--index',str(path))
 run('git','rm','--','.github/scripts/apply_local_text_boundary.py',str(path))
 run('git','config','user.name','github-actions[bot]');run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
 run('git','commit','-m','fix(v3): yield always-on-top HUD to recovery and report rejected continuation')
 run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
if __name__=='__main__':main()
