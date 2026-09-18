# Pocket Composer v3 候选说明

这是隔离分支 `v3/00-baseline` 上的预览候选，**不是稳定日用替换**。没有自动 merge、没有 v* tag、没有 GitHub Release。

校验值见同目录 `checksums.txt`。可执行文件哈希必须与该文件一致，才能把这次试用对应到固定源码。

## 试用

1. 不要覆盖现有安装目录里的 `config.json` / `data/`。
2. 解压 onedir 后运行 `DoubaoTypelessV3Preview.exe`，或：

```
set DT_V3_DATA_DIR=%LOCALAPPDATA%\DoubaoTypeless\preview-v3
python -m doubao_typeless
```

3. 手机打开控制台里的局域网地址，输入配对码。电脑打开 `/pc` 确认插入/截图。默认不授予截图；文字同步不需要 API Key。
4. 空闲时应看不到浮窗。`Alt+I` 插入，`Alt+Shift+I` 召回上次图文（不再是跳过纠错）。语法合法不等于注册成功。
5. 退出：关控制台窗口即可。回退：继续使用原来的 `python main.py` 日用入口，不要把 preview 数据拷进日用目录。
6. 同数据目录再开一个预览实例会退出，不会强杀已运行进程。

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
| R08 配对授权 | V3-04/10/19 | 手机不能自授；PC `/pc` 可授权 | 接通，真机授权录像 BLOCKED |
| R09 无 Key 可用 | V3-18 | 无 Key 主路径；BYOK 401 保留原文 | 接通，真实付费探测未批准 |
| R10 隔离日用数据 | V3-00/21 | `DT_V3_DATA_DIR` / preview-v3 | 接通，日用切换未执行 |
| R11 隧道/新平台 | — | 明确后置，未实现 | 后置 |

## 诚实状态

- 自动测试：`python -m pytest -q`。本切片之后以 CHECKPOINT 记录的退出码为准。
- 验收定义仍在冻结目录 `docs/v3-delivery/acceptance_catalog.json`；不靠改期望换绿灯。
- HTML 设计原型不是产品 PASS。
- 真机豆包输入法、Cursor Composer 附件观测、S2/S5 独立复核：WAITING / BLOCKED_NATIVE。
- 本文件随候选提交，不构成发版授权。
