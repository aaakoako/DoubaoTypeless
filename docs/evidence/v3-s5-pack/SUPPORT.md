# V3 隔离候选支持矩阵（不是 RELEASE_READY）

审查基线：`4eb8c4454a879e6b7ce11cf47e1bb0bfdba93b9a`。产品规范：`docs/v3-product/MASTER_PLAN.md`。HTML `UI_BOARD.html` 不是产品通过。

## 包

| 包 | 控制台 | EXE SHA256 | ZIP SHA256 |
|---|---|---|---|
| DoubaoTypelessV3Preview | 有 | `fd06cfd510ea23ebb1a4c4f9051b87da8422252f5b3f86724d93df766c96f084` | `0ca992fe494c61791fa9415d9866ddd8fdb1b24076c0b2ae3cec9a9bb568a7b6` |
| DoubaoTypelessV3PreviewUI | 无 | `42dc749286afb551457abebe60aa2aafe20f3f3455a552393318a493d09063ba` | `6e4bd1f5f41c0994d1d45ad8d768aeb727834fdeb56132234247f5ba55cfcf77` |

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
- pytest 以 CHECKPOINT 记录为准

## 不能自称通过

- 真实 Android + 豆包输入法扫码/相册/白板
- 真实 Cursor Composer 图文投递（PasteTarget 不能代替）
- 独立复核签署
- merge / tag / Release

独立审阅者请从固定源码 SHA 与上表包哈希开始，不要用本文件当 PASSED。
