# 审批对象（空着 = 未授权发布）

本文件列出必须由人签署的动作。开发者不能自签 `RELEASE_READY`。

| 动作 | 对象 | 状态 |
|---|---|---|
| 功能 / 安全 / 视觉 / 包哈希独立复核 | 独立审阅者 | WAITING |
| 真机 Android + 豆包输入法 | 设备持有者 | BLOCKED_NATIVE |
| 真实 Cursor Composer 图文 | 设备持有者 | BLOCKED_NATIVE |
| merge 到 master | 仓库所有者 | 未批准 |
| 打 v* tag | 仓库所有者 | 未批准 |
| GitHub Release | 仓库所有者 | 未批准 |
| 覆盖日用安装 / 改日用默认 | 日用使用者 | 未批准 |

复核入口：`SUPPORT.md`、`GETTING_STARTED.md`、`MIGRATION.md`、本目录 `pack.json` / `windowed.json` 的 EXE/ZIP SHA256。源码 commit 不等于包哈希。当前包绑定本切片提交后的实际 HEAD。
