"""Pinned official portable NSIS toolchain; SHA checked before extracting."""
import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen
import zipfile

SHA='56581f90db321581c5381193d796fffcf2d24b2f8fed2160a6c6a3baa67f2c4f'
URL='https://downloads.sourceforge.net/project/nsis/NSIS%203/3.12/nsis-3.12.zip'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    root=a.directory.resolve();root.mkdir(parents=True,exist_ok=True)
    archive=root/'nsis-3.12.zip'
    if not archive.exists():
        with urlopen(URL,timeout=60) as response:archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA:raise ValueError('NSIS checksum mismatch')
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            if not (root/item.filename).resolve().is_relative_to(root):raise ValueError('Unsafe archive path')
        z.extractall(root)
    print(root/'nsis-3.12/makensis.exe')
