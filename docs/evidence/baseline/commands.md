# V3-00 实际命令与退出码

审查基线 / 初始 HEAD: e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5
分支: v3/00-baseline（从 master 新建，未 merge、未推送、未打 v* 标签）
隔离运行时: G:\DoubaoTypeless\preview-v3-00（detached worktree，写入其 config.json，未写仓库日用 config.json）

| 命令 | 退出码 | 观察 |
|---|---|---|
| git rev-parse HEAD（开始） | 0 | e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5 |
| git status --short --branch | 0 | master 干净，后切到 v3/00-baseline |
| git worktree add --detach G:\DoubaoTypeless\preview-v3-00 e6b5b08 | 0 | 隔离运行时 |
| python -m pytest -q tests/test_v3_00_baseline.py（RED） | 1 | 10 failed，缺夹具/证据 |
| python -m pip install pytest jsonschema customtkinter pynput pystray qrcode[pil] httpx | 0 | |
| python -m playwright install chromium | 0 | chrome.exe exists True |
| python tools/v3_00_freeze.py | 0 | AC3-001/004 PASS |
| python tools/v3_00_native_harness.py（第1次） | 0 | inserted=false；合成 Alt+I 未插入 |
| python tools/v3_00_native_harness.py（第2次） | 0 | paste_sent=True，目标未收到 |
| python tools/v3_00_native_harness.py（第3次） | 0 | inserted=true；目标窗可见中文/换行/Opus |
| python docs/pocket-composer-v3/tools/check_prototype.py | 0 | 34/34；非产品 PASS |
| python docs/pocket-composer-v3/tools/check_contracts.py | 0 | 25/25 |
| python docs/pocket-composer-v3/tools/check_handoff.py（默认 GBK） | 1 | UnicodeDecodeError |
| $env:PYTHONUTF8=1; python docs/pocket-composer-v3/tools/check_handoff.py | 0 | PASS；acceptance 仍 NOT_RUN |
| python -m pytest -q | 0 | 23 passed |
| python -m py_compile main.py ... tests/test_v3_00_baseline.py tools/v3_00_*.py | 0 | |
| Test-Path config.json | 0 | REPO_CONFIG_ABSENT |

未执行: git reset、覆盖日用数据、git push、推 v* 标签、发布 Release、展开 V3-01 及之后卡片。
