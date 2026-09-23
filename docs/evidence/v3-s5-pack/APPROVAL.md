# 审批对象（空着 = 未授权发布）

本文件列出必须由人签署的动作。开发者不能自签 `RELEASE_READY`。

| 动作 | 对象 | 状态 |
|---|---|---|
| 安全独立复核 | Security Review `63a48a14` | PASS（见 INDEPENDENT_REVIEW.md） |
| Bugbot 独立复核 | Bugbot `44caa116` | REQUEST_CHANGES，CI/属主返修已落地；AGENTS.md 冻结未改 |
| 视觉 / 包哈希人类签署 | 独立审阅者 | WAITING |
| 真机 Android + 豆包输入法 | 设备持有者 | BLOCKED_NATIVE |
| 真实 Cursor Composer 图文 | 设备持有者 | BLOCKED_NATIVE |
| RELEASE_READY | 不得自签 | 未达（上列未签署项仍卡） |
| merge 到 master | 仓库所有者 | 未批准 |
| 打 v* tag | 仓库所有者 | 未批准 |
| GitHub Release | 仓库所有者 | 未批准 |
| 覆盖日用安装 / 改日用默认 | 日用使用者 | 未批准 |

复核入口：`SUPPORT.md`、`GETTING_STARTED.md`、`MIGRATION.md`、本目录 `pack.json` / `windowed.json` 的 EXE/ZIP SHA256。源码 commit 不等于包哈希。当前包绑定本切片提交后的实际 HEAD。
