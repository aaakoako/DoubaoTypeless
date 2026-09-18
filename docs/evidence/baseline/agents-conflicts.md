# AGENTS.md 与 v3 冲突（只记录，不机械沿用）

审查基线仍是 `e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5`。V3-00 不改这些旧入口。

| AGENTS.md / 旧实现 | v3 硬边界 |
|---|---|
| CustomTkinter 审阅窗常驻可唤起，`show_recording` 里 `focus_force`，最小 460×360，默认几何 560×440 | 空闲完全无浮窗；输入 HUD 360×88/132 且不抢焦点 |
| `phone.html` 单页文本框 + 发送按钮；插入后 `cleared` 直接清空当前输入 | 单页 Composer；截图/相册/白板共用编辑器；归档必须匹配稿件身份，禁止无条件 clear |
| 前台纠错 + 后台学习两套 LLM | 无 Key 图文闭环；BYOK 仅为手动文字旁路 |
| Alt+Shift+I = 审阅窗内跳过纠错并插入 | 新键位为召回重试，迁移时不能双重执行 |
| `typer.paste_text` 只贴文字；`paste_sent` 当插入结果 | 先图后文；系统发键 ≠ 目标收到；不可观察则 UNKNOWN |
| aiohttp 文本 WS，无图片资产合同 | dt.v3 + 二进制 HTTP 传图 |
| 首选保持现有 Python/CustomTkinter | 新桌面范围首选 PySide6 Widgets，G0 未过则短期保留旧 UI |
| 不提白板 | 本轮完整范围含轻量白板，不能后置到下一版；本卡 V3-00 只冻结基线，实现在 V3-13 |

旧文字闭环必须在隔离数据下实测并记录，失败不得改写成通过。
