"""完整 onedir 内容清单；不能用单EXE哈希冒充整包校验。无发布操作。"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def make_manifest(root: Path, source_sha: str, output: Path):
    root=root.resolve(strict=True); output=output.resolve()
    if not root.is_dir():raise ValueError('candidate root must be a directory')
    if output==root or root in output.parents:raise ValueError('manifest output must be outside candidate root')
    if len(source_sha)!=40 or any(c not in '0123456789abcdef' for c in source_sha):raise ValueError('full source SHA required')
    items=[]
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('symlinks are not allowed in candidate')
        if path.is_file():
            with path.open('rb') as stream:
                digest=hashlib.file_digest(stream,'sha256').hexdigest()
            items.append({'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':digest})
    if not items:raise ValueError('empty candidate')
    doc={'source_sha':source_sha,'release_ready':False,'files':items}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
    return doc


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    parser.add_argument('--source-sha',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();make_manifest(args.root,args.source_sha,args.output)
