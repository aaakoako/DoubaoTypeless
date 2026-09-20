"""Import a fixed product-only delta using ordinary contents permission.
Workflow restoration is a separate authorized connector operation, not a CI write.
"""
import base64,hashlib,lzma,os,subprocess,tempfile
from pathlib import Path
BASE='b84b797f9e3e97814cbf66aa02866d031465b470'
BRANCH='v3/assistant-runtime-safety'
DIGEST='02ed90617df803d3a8418b7c840c5e347a42fa4033b60bab902bc4c11c6c6d9e'
FILES={'docs/v3-product/MASTER_PLAN.md','src/doubao_typeless/adapters/composer_scope.py','src/doubao_typeless/adapters/cursor_windows.py','src/doubao_typeless/app.py','src/doubao_typeless/platform/windows/composer_locator.py','src/doubao_typeless/platform/windows/focus.py','src/doubao_typeless/platform/windows/native_input.py','src/doubao_typeless/services/bridge_v3.py','src/doubao_typeless/services/phone_send.py','src/doubao_typeless/storage/settings_store.py','src/doubao_typeless/ui/desktop.py','src/doubao_typeless/ui/hud.py','tests/test_v3_editor_transactions.py','tests/test_v3_frontend_prod.py','tests/test_v3_phone_send.py','tests/test_v3_structural_composer.py','tools/verify_candidate_browser.py','web/src/app.ts','web/src/styles.css'}
def run(*a,**kw):return subprocess.run(a,check=True,**kw)
def main():
 if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('wrong branch')
 if run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()!=BASE:raise RuntimeError('wrong parent')
 folder=Path('.github/final-delta');chunks=sorted(folder.glob('part-*.txt'))
 if [p.name for p in chunks]!=[f'part-{i}.txt' for i in range(3)]:raise RuntimeError('wrong chunks')
 patch=lzma.decompress(base64.b64decode(''.join(p.read_text().strip() for p in chunks),validate=True),memlimit=256*1024*1024)
 if len(patch)!=101324 or hashlib.sha256(patch).hexdigest()!=DIGEST:raise RuntimeError('patch integrity')
 with tempfile.NamedTemporaryFile(suffix='.patch') as f:
  f.write(patch);f.flush()
  listing=run('git','apply','--numstat',f.name,capture_output=True,text=True).stdout
  if {x.split('\t',2)[2] for x in listing.splitlines()}!=FILES:raise RuntimeError('wrong files')
  run('git','apply','--check','--index',f.name);run('git','apply','--index',f.name)
 # Strengthen the upload spy: observe the real init endpoint and require a positive control.
 test=Path('tests/test_v3_editor_transactions.py')
 if hashlib.sha256(test.read_bytes()).hexdigest()!='5df7d345519f2c8be71043e84ef850994bc5343937119447b2221627e6517e8b':raise RuntimeError('test changed')
 text=test.read_text().replace("req.url.endswith('/v3/uploads')","req.url.endswith('/v3/assets/init')").replace('original_uploads=len(uploads)','original_uploads=len(uploads)\n            assert original_uploads==1,uploads').replace('count=len(uploads)\n','count=len(uploads)\n            assert count==1,uploads\n')
 test.write_text(text)
 if hashlib.sha256(test.read_bytes()).hexdigest()!='0d66d75c878f64752d4522307167227f0303d7d8b325b67d9b9de77e9e981066':raise RuntimeError('test transformation')
 run('python','-m','compileall','-q','src','tools','tests')
 run('npm','ci',cwd='web');run('npm','run','typecheck',cwd='web');run('npm','run','build',cwd='web')
 run('git','add','-A','--','web/dist',str(test))
 run('git','rm','-r','--','.github/final-delta')
 staged=run('git','diff','--cached','--name-only',capture_output=True,text=True).stdout.splitlines()
 if any(p.startswith('.github/workflows/') for p in staged):raise RuntimeError('CI must not write workflows')
 run('git','config','user.name','github-actions[bot]');run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
 run('git','commit','-m','feat(v3): transactional editing, one-click ordered images and separately confirmed phone send')
 run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
 print('Exact source committed. Downstream checks bind to this commit; workflow itself was not changed.')
if __name__=='__main__':main()
