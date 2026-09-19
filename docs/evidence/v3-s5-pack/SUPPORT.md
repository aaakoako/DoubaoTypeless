# V3 隔离候选支持矩阵（不是 RELEASE_READY）

审查基线：`4eb8c4454a879e6b7ce11cf47e1bb0bfdba93b9a`。产品规范：`docs/v3-product/MASTER_PLAN.md`。HTML `UI_BOARD.html` 不是产品通过。

## 包

| 包 | 控制台 | EXE SHA256 | ZIP SHA256 |
|---|---|---|---|
| DoubaoTypelessV3Preview | 有 | `1bf29ff452495c3a1f3b0483834a3706b078e0019472ad83b522c586885a5f39` | `2a08aba77fa460966654eea52eeca9785567f060fa564adc5eccd145e45cfa6d` |
| DoubaoTypelessV3PreviewUI | 无 | `f9d1fae52516368183cd451c05ebc9fec357131a78eac0b171401cbf2057b976` | `710714ef365e5ad6229faefadf3737886a3071a193a22ba6164f3b0d5d91b3de` |

两份包都未签名，不是 GitHub Release，源码 SHA 不等于包哈希。

## 已实现且有自动化证据

- 插入并复制、只复制、新稿、召回保留当前稿
- 电脑改字时停放手机 WS；撤销会话断开对应 WS
- BYOK 使用所选模型；密钥不进 settings.json
- 配对长码进 QR，短码备用
- 素材所有权绑定会话
- 预览管道/数据目录/自启动名与日用 `DoubaoTypeless` 隔离
- pytest 140 passed（本切片）

## 不能自称通过

- 真实 Android + 豆包输入法扫码/相册/白板
- 真实 Cursor Composer 图文投递（PasteTarget 不能代替）
- 独立复核签署
- merge / tag / Release

独立审阅者请从固定源码 SHA 与上表包哈希开始，不要用本文件当 PASSED。
