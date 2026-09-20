"""Exact three-file correction, no CI workflow write."""
import os,hashlib,subprocess
from pathlib import Path
BRANCH='v3/assistant-runtime-safety'
def run(*a,**kw):return subprocess.run(a,check=True,**kw)
def main():
 if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('branch')
 if run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()!='dab3606c0b6369478fac502b88ca15c322f97440':raise RuntimeError('parent')
 p=Path('.github/final-delta/fix.patch')
 if hashlib.sha256(p.read_bytes()).hexdigest()!='8ae8f87938c08ab529eb39e3c56b136820c2691a838b46eb1f96403cdf0b972a':raise RuntimeError('integrity')
 run('git','apply','--check','--index',str(p));run('git','apply','--index',str(p))
 run('git','rm','-r','--','.github/final-delta')
 run('git','config','user.name','github-actions[bot]');run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
 run('git','commit','-m','fix(v3): preserve legacy receipt ordering and exercise real editor quota recovery')
 run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
if __name__=='__main__':main()
