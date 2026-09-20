"""验证隔离 Windows 冻结包的启动、HTTP存活与正常退出。

不粘贴、不截图、不访问用户数据、不宣称Cursor/手机已验收。
只对本脚本创建的进程做生命周期管理，所有运行数据置于临时目录。
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import urlopen
import uuid


def verify(exe: Path, report: Path) -> int:
    if sys.platform != 'win32':
        raise RuntimeError('This check requires Windows; not a cross-platform native claim')
    exe=exe.resolve(strict=True)
    result={'test':'frozen-startup-and-graceful-exit','executable':str(exe),'passed':False,
            'insertion_tested':False,'cursor_tested':False,'phone_tested':False}
    with tempfile.TemporaryDirectory(prefix='dt-v3-frozen-') as temp:
        data=Path(temp)/'data'
        env={**os.environ,'DT_V3_DATA_DIR':str(data),'DT_V3_PIPE':'DT-V3-smoke-'+uuid.uuid4().hex}
        child=subprocess.Popen([str(exe),'--minimized'],env=env)
        result['pid']=child.pid
        try:
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                if child.poll() is not None:
                    raise RuntimeError('candidate exited before becoming ready')
                note=data/'pair.txt'
                if note.is_file():
                    port=urlparse(note.read_text(encoding='utf-8').splitlines()[0]).port
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/v3/status',timeout=1) as response:
                            status=json.load(response)
                        if status.get('protocol')==3:
                            break
                    except OSError:
                        pass
                time.sleep(.15)
            else: raise RuntimeError('startup deadline exceeded')
            result['protocol_ready']=True
            # 同一隔离管道的真实退出入口，不用结束进程冒充退出通过。
            quit_command=subprocess.run([str(exe),'--quit'],env=env,timeout=15)
            result['quit_command_exit']=quit_command.returncode
            if quit_command.returncode!=0: raise RuntimeError('quit command failed')
            result['process_exit']=child.wait(timeout=15)
            result['passed']=result['process_exit']==0
        except Exception as exc:
            result['error_type']=type(exc).__name__
            result['passed']=False
        finally:
            if child.poll() is None:
                # 只清理本脚本刚创建的PID；结果仍失败，绝不称正常退出。
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait()
                result['test_owned_process_cleanup']=True
            report.parent.mkdir(parents=True,exist_ok=True)
            # 只保留该次隔离进程的运行日志，不复制pair.txt、截图或凭据。
            log_dir = report.parent / (report.stem + "-logs")
            for name in ("runtime.log", "v3.log"):
                path = data / "logs" / name
                if path.is_file():
                    log_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, log_dir / name)
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(verify(args.exe,args.report))
