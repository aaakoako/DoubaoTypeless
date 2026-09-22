"""Package the entire frozen folder and compile the current-user installer."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import zipfile
from manifest_candidate import make_manifest

ROOT=Path(__file__).resolve().parents[1]

def package(payload, output, compiler, test=False):
    info=json.loads((payload/'_internal/build-info.json').read_text(encoding='utf-8'))
    expected=json.loads((ROOT/'build-info.json').read_text(encoding='utf-8'))
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if info != expected or info.get('source_sha') != head:
        raise ValueError('Payload does not match the prepared source commit')
    subprocess.run(['git','diff','--exit-code','HEAD'],cwd=ROOT,check=True)
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    # Workflow evidence is generated after source binding. It is never bundled.
    if any(not p.startswith('evidence/') for p in untracked):
        raise ValueError('Untracked files outside the explicit evidence directory')
    if info['channel'] not in {'release-candidate','stable'}:
        raise ValueError('Not a release payload')
    shutil.copy2(ROOT/'docs/release/v3-installation.md',payload/'使用说明.md')
    version=info['version']
    output.mkdir(parents=True,exist_ok=True)
    prefix=f'DoubaoTypeless_{version}_win_x64'
    if test: prefix+='-installer-test'
    installer=output/(prefix+'_Setup.exe')
    args=[str(compiler),'/INPUTCHARSET','UTF8',f'/DVERSION={version}',f'/DPAYLOAD={payload.resolve()}',f'/DOUTPUT={installer.resolve()}']
    if test: args.append('/DTEST_INSTALL')
    subprocess.run([*args,str(ROOT/'packaging/windows-installer.nsi')],check=True,cwd=ROOT)
    if not test:
        make_manifest(payload,info['source_sha'],output/(prefix+'_files.json'))
        archive=output/(prefix+'_portable.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(payload.rglob('*')):
                if p.is_file():z.write(p,Path('DoubaoTypeless')/p.relative_to(payload))
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
        (output/'SHA256SUMS.txt').write_text('\n'.join(
            hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name for p in [installer,archive])+'\n',encoding='utf-8')
    return installer

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('payload',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True)
    p.add_argument('--test-install',action='store_true')
    a=p.parse_args();print(package(a.payload,a.output,a.compiler,a.test_install))
