# V3 已知限制与回退（任务未完成）

日期按 CHECKPOINT。这不是发版授权。

## 已由开发者接通并复跑

- 隔离 Windows 图形入口：二维码、配对、托盘、设置、图文详情、恢复对话。
- 正式前端文字：生产页 POST `/v3/pair` 只带 code → 桌面批准插入 → 草稿进入详情 → 指定文本目标收到原文，不发 Enter。
- 图文：生产页裁剪/遮挡/编号 → 分块上传 → 先图后文进入指定粘贴目标；成品 SHA ≠ 源图。
- 白板/多图/召回：空白板不能完成；撤销重做；召回不吞当前稿；重启字节可恢复。
- BYOK 失败保留原文；UNKNOWN 插入弹出恢复选择，不自动重贴。
- 隔离包二次启动唤起；`--quit` 与托盘退出同一路径，进程自行结束，HTTP 停止。未用 taskkill。

## 明确未通过（因此任务未完成）

| 缺失环境 | 受阻用例 | 最小操作 |
|---|---|---|
| 真实 Android + 豆包输入法 | 真机引导、语音、相册、白板手感、长连接 | 手机扫窗口二维码，与电脑同一局域网，配对后按产品步骤走一遍并录屏 |
| Cursor Composer 可观察 UIA（本机 Python 3.13 无 comtypes） | 主目标一键图文 | 对真实 Composer 列出可验证字段，或另行批准半自动降级；指定粘贴目标 CONFIRMED 不能写成 Cursor PASS |
| 独立审阅者 | RELEASE_READY / 公开发布 | 按证据目录核对 SHA、包哈希、授权与图文 |

## 迁移与回退

- V3 数据在 `%LOCALAPPDATA%\DoubaoTypeless\preview-v3` 或 `DT_V3_DATA_DIR`，不写日用 `config.json`。
- 开机自启注册表名 `DoubaoTypelessV3Preview`，不是日用 `DoubaoTypeless`。
- 回退：继续用原来的 `python main.py` 日用入口；不要把 preview 数据拷进日用目录。
- `pc.html` 仅诊断，普通使用走桌面窗口。
