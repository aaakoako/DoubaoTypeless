#!/usr/bin/env python3
"""
本地试跑「检查更新」逻辑（不修改仓库里的 app_version.py）。

请在项目根目录执行：
  python scripts/test_update.py
  python scripts/test_update.py --fake-old 0.0.1

--fake-old：假装本机版本更旧，便于走「发现新版本」分支（源码运行会提示去 Release，不会下载替换 exe）。
完整「下载 + bat 替换」需用旧版打包 exe + Release 上已有新版 exe 自测。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    p = argparse.ArgumentParser(description="本地测试 updater.run_update_flow")
    p.add_argument(
        "--fake-old",
        metavar="VER",
        default=None,
        help="假装本机版本（如 0.0.1），触发与远端的版本比较；勿在 import updater 前写死到文件",
    )
    args = p.parse_args()

    import app_version

    if args.fake_old:
        app_version.APP_VERSION = args.fake_old.strip()

    from updater import run_update_flow

    async def _run() -> None:
        def log(s: str) -> None:
            print(s)

        msg = await run_update_flow(log=log)
        print("\n=== 返回（与设置里弹窗一致）===\n" + msg)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
