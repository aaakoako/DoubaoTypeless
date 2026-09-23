# V3 隔离候选支持矩阵（不是 RELEASE_READY）

审查基线：`4eb8c4454a879e6b7ce11cf47e1bb0bfdba93b9a`。产品规范：`docs/v3-product/MASTER_PLAN.md`。HTML `UI_BOARD.html` 不是产品通过。

## 包

| 包 | 控制台 | EXE SHA256 | ZIP SHA256 |
|---|---|---|---|
| DoubaoTypelessV3Preview | 有 | `035fca0bc7945e45e2338c4ed481887e548b7aec09fbe4b3a8bd14542b1c0677` | `53bda5fb1c7a8f3a2bda3071f409e6e48d13c880d7bc0b12d2a9088ebe5db21a` |
| DoubaoTypelessV3PreviewUI（本轮） | 无 | `5891472bb331b2e2bf15fc1057d3d62b6fe94f6ddf0c82d0754404c8288d4538` | `6fdc6137d0ef0e5c84ce09db0b02f7d46dd26b9c43bca5f3a047a8facce5e9cd` |
| DoubaoTypelessV3PreviewUI（旧 A03，不得沿用） | 无 | `4bae6609e4b5af5e6c8508b774bb7b023b4c0462dd43625e95f96ee9617ae00f` | `f23be749dbc35c89e7e8f5a909c1f041ac33e0ffbd48ed691262336d853181df` |

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
