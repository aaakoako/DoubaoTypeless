# Pocket Composer v3 工程预览说明

这是隔离分支 `v3/00-baseline` 上的工程预览，**不是稳定日用替换**，**桌面产品交付尚未完成**。没有自动 merge、没有 v* tag、没有 GitHub Release。

不要把当前包描述成“只剩用户核查或独立审阅”。

校验值见同目录 `checksums.txt`。可执行文件哈希必须与该文件一致，才能把这次试用对应到固定源码。

## 试用

1. 不要覆盖现有安装目录里的 `config.json` / `data/`。
2. 解压 onedir 后双击 `DoubaoTypelessV3Preview.exe`。应出现连接窗口（二维码、地址、配对码），而不是只靠控制台。
3. 用手机浏览器扫码或打开窗口里的地址。电脑窗口里批准插入/截图。不必打开 `pc.html`、不必读 `pair.txt`、不必改 JSON、不必设环境变量。
4. 不配模型 Key 也能用文字、图片和白板。设置页可填 Base URL / Key / 模型并测试连接。
5. 空闲无输入浮窗。需要时点「展开」改字，或用「当前图文」。`Alt+I` 插入，`Alt+Shift+I` 召回。语法合法不等于注册成功。
6. 关闭连接窗口会收到托盘，连接保持。托盘「退出」才结束进程。再双击 EXE 应唤起已有窗口，不启动第二套服务。
7. 回退：继续使用原来的 `python main.py` 日用入口，不要把 preview 数据拷进日用目录。
8. 本预览包仍带控制台，便于启动失败时对照文件日志；**只把 console 改成 False 不算修复**。日志在隔离数据目录 `logs/v3.log`。

## 需求追溯

| 需求 | 任务 | 当前证据 | 产品声明 |
|---|---|---|---|
| R01 空闲无浮窗 | V3-01/07 | HUD 默认隐藏；10min 无手机采样 `docs/evidence/v3-idle/`；真机长连接仍 BLOCKED | 接通，真机未验 |
| R02 单页 Composer | V3-02/09 | 产品源 `web/` Vite+Konva；`composer.html` 仅 fallback | 接通 |
| R03 轻量白板 | V3-12/13 | S3 生产页白板+撤销重做 | 接通，真机触控 BLOCKED |
| R04 先图后文、不发 Enter | V3-15 | S2/S3 指定粘贴目标 CONFIRMED；Cursor 附件 BLOCKED_NATIVE | 指定目标接通，不是 Cursor |
| R05 召回且重核目标 | V3-16 | 召回不吞当前稿；UNKNOWN 不自动重放 | 接通 |
| R06 同步不发键 | V3-04/06 | 重连不 insert；未授权零副作用 | 接通 |
| R07 图片原子落盘 | V3-05/17 | SQLite + 分块；重启字节可恢复 | 接通 |
| R08 配对授权 | V3-04/10/19 | 手机不能自授；桌面窗口可授权；`/pc` 仅诊断 | 桌面入口接通，真机授权录像 BLOCKED |
| R09 无 Key 可用 | V3-18 | 无 Key 主路径；BYOK 401 保留原文 | 接通，真实付费探测未批准 |
| R10 隔离日用数据 | V3-00/21 | `DT_V3_DATA_DIR` / preview-v3 | 接通，日用切换未执行 |
| R11 隧道/新平台 | — | 明确后置，未实现 | 后置 |

## 诚实状态

- 自动测试：`python -m pytest -q`。本切片之后以 CHECKPOINT 记录的退出码为准。
- 验收定义仍在冻结目录 `docs/v3-delivery/acceptance_catalog.json`；不靠改期望换绿灯。
- HTML 设计原型不是产品 PASS。当前截图来自原生 Qt 窗口 + 正式 V3 服务。
- 桌面图形入口已在源码接通，完整候选仍缺：用**同一份新包**做启动到退出、真机图文、Cursor 观测、独立复核。
- 真机豆包输入法、Cursor Composer 附件观测：BLOCKED_NATIVE，只阻塞相应验证。
- 本文件随预览提交，不构成发版授权。
