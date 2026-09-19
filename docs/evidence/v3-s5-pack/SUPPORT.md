# V3 隔离候选支持矩阵（不是 RELEASE_READY）

审查基线：`4eb8c4454a879e6b7ce11cf47e1bb0bfdba93b9a`。产品规范：`docs/v3-product/MASTER_PLAN.md`。HTML `UI_BOARD.html` 不是产品通过。

## 包

| 包 | 控制台 | EXE SHA256 | ZIP SHA256 |
|---|---|---|---|
| DoubaoTypelessV3Preview | 有 | `eab2e68ff0793ef157b70300f82e85c1576e63edcd7058a69802e4ae294fa84c` | `eac99f3662577d3624f1b3fe4150396ed68410d898560c46024a2cf221d33f5c` |
| DoubaoTypelessV3PreviewUI | 无 | `ec137b462b43de7ccca095ee975c9065f936c45936c99fb5ec13471e04e4a7fe` | `c5539fc1d82dd0b1bf1b1bd5306f002e4c6e565823e6791131d33a047479f5a7` |

两份包都未签名，不是 GitHub Release，源码 SHA 不等于包哈希。

## 已实现且有自动化证据

- 插入并复制、只复制、新稿、召回保留当前稿
- 电脑改字时停放手机 WS；撤销会话断开对应 WS
- BYOK 使用所选模型；密钥不进 settings.json
- 配对长码进 QR，短码备用
- 素材所有权绑定会话
- 预览管道/数据目录/自启动名与日用 `DoubaoTypeless` 隔离
- 检查更新只打开公开下载页，不自动替换
- 日用词库只读导入；`DT_V3_TARGET_STATE` 单独存在不能当正式确认
- 当前图文有图序缩略图；模型建议可采纳/拒绝；手机可起名
- pytest 以 CHECKPOINT 记录为准

## 不能自称通过

- 真实 Android + 豆包输入法扫码/相册/白板
- 真实 Cursor Composer 图文投递（PasteTarget 不能代替）
- 独立视觉 / 包哈希人类签署
- 独立复核已记录 ≠ RELEASE_READY
- merge / tag / Release

独立审阅者请从固定源码 SHA 与上表包哈希开始，不要用本文件当 PASSED。
