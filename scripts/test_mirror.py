#!/usr/bin/env python3
"""
探测「检查更新」各数据源是否连通（直连 → 国内镜像）。

项目根目录执行: python scripts/test_mirror.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    # 避免本地已设 DT_GITHUB_MIRROR 干扰「默认策略」展示时，可先注释下行或临时 unset
    print("DT_GITHUB_MIRROR =", repr(os.environ.get("DT_GITHUB_MIRROR", "<未设置>")))
    print()

    import updater

    print("API 尝试顺序:")
    for url, label, pref in updater._api_try_plan():
        extra = f" → 前缀 {pref!r}" if pref else ""
        print(f"  - {label}{extra}")
        print(f"    {url[:88]}..." if len(url) > 88 else f"    {url}")
    print()

    async def probe() -> None:
        def log(s: str) -> None:
            print(s)

        data, via = await updater.fetch_latest_release(log=log)
        print()
        if data:
            tag = str(data.get("tag_name", ""))
            print(f"结果: 成功 tag={tag!r}")
            print(f"元数据来源: {'直连' if via is None else '镜像前缀 ' + via!r}")
        else:
            print("结果: 全部失败（请检查网络或镜像可用性）")

    asyncio.run(probe())


if __name__ == "__main__":
    main()
