"""Exact source-only surface ownership patch; remove transport after applying."""
import hashlib,os,subprocess
from pathlib import Path
BRANCH='v3/assistant-runtime-safety'
BASE='a806931f5480c13e95b93abe89c500b8eac0b382'
DIGEST='75275bcef305de07fb792574e4b9b567e49dca92d20df403105eb52e391d7255'
FILES={'src/doubao_typeless/ui/desktop.py','src/doubao_typeless/ui/hud.py','tools/verify_candidate_browser.py'}
def run(*a,**kw):return subprocess.run(a,check=True,**kw)
def main():
 if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('wrong branch')
 if run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()!=BASE:raise RuntimeError('wrong parent')
 path=Path('.github/scripts/surface_delta.patch')
 # Transport may prefix a diff header with one space; canonicalize headers only.
 data=path.read_bytes().replace(b'\n diff --git ',b'\ndiff --git ')
 if hashlib.sha256(data).hexdigest()!=DIGEST:raise RuntimeError('wrong patch')
 path.write_bytes(data)
 listing=run('git','apply','--numstat',str(path),capture_output=True,text=True).stdout
 if {x.split('\t',2)[2]for x in listing.splitlines()}!=FILES:raise RuntimeError('wrong files')
 run('git','apply','--check','--index',str(path));run('git','apply','--index',str(path))
 run('git','rm','-f','--','.github/scripts/apply_local_text_boundary.py',str(path))
 run('git','config','user.name','github-actions[bot]');run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
 run('git','commit','-m','fix(v3): prevent the HUD intercepting expanded-window actions')
 run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
if __name__=='__main__':main()
