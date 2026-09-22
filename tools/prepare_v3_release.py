"""Bind a clean source commit to release artifacts. Does not publish anything."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from doubao_typeless.build_info import VERSION

def prepare(channel, tag=None):
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise RuntimeError('Commit source changes before generating release identity')
    if tag is not None and tag != 'v'+VERSION:
        raise RuntimeError(f'Tag {tag} does not match source version {VERSION}')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    info={'source_sha':sha,'version':VERSION,'channel':channel,'release_ready':False}
    (ROOT/'build-info.json').write_text(json.dumps(info),encoding='utf-8')
    from comtypes.client import GetModule
    GetModule('UIAutomationCore.dll')
    from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
    number=tuple(map(int,VERSION.split('.')))+(0,)
    resource=VSVersionInfo(ffi=FixedFileInfo(filevers=number,prodvers=number,mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),
        kids=[StringFileInfo([StringTable('040904B0',[
            StringStruct('FileDescription',f'DoubaoTypeless {channel} {sha[:8]}'),
            StringStruct('FileVersion',VERSION),StringStruct('ProductName','DoubaoTypeless'),
            StringStruct('ProductVersion',VERSION),StringStruct('OriginalFilename','DoubaoTypeless.exe')])]),
            VarFileInfo([VarStruct('Translation',[1033,1200])])])
    resource_path=ROOT/'build/v3-version.txt';resource_path.parent.mkdir(exist_ok=True)
    resource_path.write_text(str(resource),encoding='utf-8')
    print(json.dumps(info))
    return info

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--channel',choices=['release-candidate','stable'],default='release-candidate')
    p.add_argument('--tag')
    a=p.parse_args();prepare(a.channel,a.tag)
