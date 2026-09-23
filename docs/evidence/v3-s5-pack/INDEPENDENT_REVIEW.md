# 独立复核记录 — 不是 RELEASE_READY

实现者不能自签产品通过。本文件记录本轮已启动的独立审阅结论，并明确未签署项。

## 已记录的独立结论

| 审阅 | 标识 | 结论 |
|---|---|---|
| Security Review | `63a48a14-f786-41eb-8406-03ae50188fb9` | PASS |
| Bugbot | `44caa116-934d-4037-8305-de2dfe9ccffc` | REQUEST_CHANGES，返修见下 |

安全审查覆盖配对/撤销/WS、素材 GET 属主、BYOK 密钥、日用隔离、观察器门闩、自家窗口不当粘贴目标。明文局域网按产品接受。遗留的旧 `POST /v3/assets` 属主绑定已在本切片补上，并由 `test_legacy_asset_post_binds_owner` 证伪。

## Bugbot 返修

1. **CI 打包缺 qrcode/httpx（高）**：`.github/workflows/preview-v3.yml` 的 `windows-min-pack` 已安装这两项；测试读取该步骤文本。
2. **AGENTS.md 预览命令不可运行（中）**：`AGENTS.md` 在 AC3-004 日用指纹里，不能改写换绿灯。正确命令写在产品入口 `docs/v3-product/START_HERE.md`：`PYTHONPATH=src` + `python tools/run_v3.py`。

## 仍未签署（卡 RELEASE_READY）

- 视觉对照 `UI_BOARD.html` 的真人/独立视觉签署
- 包哈希的独立人类核对（实现者重建不算自签通过）
- 真实 Android + 豆包输入法
- 真实 Cursor Composer（PasteTarget 不能代替）
- merge / tag / GitHub Release / 覆盖日用

结论只能停在「独立复核已记录」。不得把本文件写成 RELEASE_READY 或 PUBLISHED。
