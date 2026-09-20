"""Import one fixed product delta, rebuild frontend, remove transport, restore read-only CI.
Only fast-forward the authorized isolated branch; never merge, release or use user data.
"""
import base64, hashlib, lzma, os, subprocess, tempfile
from pathlib import Path
BASE='5198c5c888af9541e118d82dc1026655abb9dceb'
BRANCH='v3/assistant-runtime-safety'
DIGEST='02ed90617df803d3a8418b7c840c5e347a42fa4033b60bab902bc4c11c6c6d9e'
WORKFLOW='21c4e980a9c5a0a7e93101e59ab3389e1908a6d417cf301f8a2257c71f38d615'
FILES={'docs/v3-product/MASTER_PLAN.md','src/doubao_typeless/adapters/composer_scope.py','src/doubao_typeless/adapters/cursor_windows.py','src/doubao_typeless/app.py','src/doubao_typeless/platform/windows/composer_locator.py','src/doubao_typeless/platform/windows/focus.py','src/doubao_typeless/platform/windows/native_input.py','src/doubao_typeless/services/bridge_v3.py','src/doubao_typeless/services/phone_send.py','src/doubao_typeless/storage/settings_store.py','src/doubao_typeless/ui/desktop.py','src/doubao_typeless/ui/hud.py','tests/test_v3_editor_transactions.py','tests/test_v3_frontend_prod.py','tests/test_v3_phone_send.py','tests/test_v3_structural_composer.py','tools/verify_candidate_browser.py','web/src/app.ts','web/src/styles.css'}
def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def main():
 if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('wrong branch')
 if run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()!=BASE:raise RuntimeError('wrong parent')
 folder=Path('.github/final-delta')
 chunks=sorted(folder.glob('part-*.txt'))
 if [p.name for p in chunks]!=[f'part-{i}.txt' for i in range(3)]:raise RuntimeError('wrong chunks')
 patch=lzma.decompress(base64.b64decode(''.join(p.read_text().strip() for p in chunks),validate=True),memlimit=256*1024*1024)
 if len(patch)!=101324 or hashlib.sha256(patch).hexdigest()!=DIGEST:raise RuntimeError('patch integrity')
 workflow=(folder/'readonly-workflow.yml').read_bytes()
 if hashlib.sha256(workflow).hexdigest()!=WORKFLOW:raise RuntimeError('workflow integrity')
 with tempfile.NamedTemporaryFile(suffix='.patch') as f:
  f.write(patch);f.flush()
  listing=run('git','apply','--numstat',f.name,capture_output=True,text=True).stdout
  if {x.split('\t',2)[2] for x in listing.splitlines()}!=FILES:raise RuntimeError('wrong files')
  run('git','apply','--check','--index',f.name);run('git','apply','--index',f.name)
 run('python','-m','compileall','-q','src','tools','tests')
 run('npm','ci',cwd='web');run('npm','run','typecheck',cwd='web');run('npm','run','build',cwd='web')
 Path('.github/workflows/assistant-candidate.yml').write_bytes(workflow)
 run('git','add','-A','--','web/dist','.github/workflows/assistant-candidate.yml')
 run('git','rm','-r','--','.github/final-delta')
 run('git','config','user.name','github-actions[bot]');run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
 run('git','commit','-m','feat(v3): transactional mobile editing, ordered multi-image delivery and separately confirmed phone send')
 run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
 print('Product source committed; all downstream tests must use this exact SHA.')
if __name__=='__main__':main()
