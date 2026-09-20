"""One exact source-only fix on the authorized isolated branch; no workflow writes.

The old/new source guards prevent overwriting concurrent work. Remove this file
in the resulting real product commit, which downstream jobs explicitly check out.
"""
import hashlib, os, subprocess
from pathlib import Path

BRANCH='v3/assistant-runtime-safety'
BASE='f3af0c528473a12f188db9763fa09ac47c92cd3e'
EXPECTED='97724a2ff153468a21853b20ba0fc65bd95d73c8def0a7e50cf0ff96138cd0ec'

def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)

def main():
    if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('wrong branch')
    parent=run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()
    if parent!=BASE:raise RuntimeError('unexpected source parent')
    p=Path('src/doubao_typeless/app.py')
    if hashlib.sha256(p.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('source changed')
    old='            if kind == "unknown" or is_own_window(*focus[:2]):\n'
    new='''            # A user-triggered local text insert is not restricted to AI composers.
            # Tk/native editors may expose no UIA editable pattern. Keep their text
            # path, but require a located composer for images or our own window.
            # DeliveryService rechecks the final bundle and target after prepare.
            if (kind == "unknown" and bool(self.draft.assets)) or is_own_window(*focus[:2]):
'''
    source=p.read_text(encoding='utf-8')
    if source.count(old)!=1:raise RuntimeError('unexpected replacement count')
    p.write_text(source.replace(old,new),encoding='utf-8')
    run('git','add','--',str(p))
    run('git','rm','--','.github/scripts/apply_local_text_boundary.py')
    run('git','config','user.name','github-actions[bot]')
    run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    run('git','commit','-m','fix(v3): preserve explicit local text insertion without requiring Composer discovery')
    run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')

if __name__=='__main__':main()
