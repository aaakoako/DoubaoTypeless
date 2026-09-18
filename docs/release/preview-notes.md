# Pocket Composer v3 候选说明

这是隔离分支 `v3/00-baseline` 上的预览候选，**不是稳定日用替换**。没有自动 merge、没有 v* tag、没有 GitHub Release。

## 试用

1. 不要覆盖现有安装目录里的 `config.json` / `data/`。
2. 运行 `scripts/启动-v3.bat`，或：

```
set DT_V3_DATA_DIR=%LOCALAPPDATA%\DoubaoTypeless\preview-v3
python -m doubao_typeless
```

3. 手机打开控制台里的局域网地址，输入配对码。默认不授予截图；文字同步不需要 API Key。
4. 空闲时应看不到浮窗。`Alt+I` 插入，`Alt+Shift+I` 召回上次图文（不再是跳过纠错）。
5. 退出：关控制台/托盘即可。回退：继续使用原来的 `python main.py` 日用入口，不要把 preview 数据拷进日用目录。

## 需求追溯

| 需求 | 任务 | 当前证据 |
|---|---|---|
| R01 空闲无浮窗 | V3-01/07 | HUD 默认隐藏；10min 采样见 `docs/evidence/v3-idle/`（真机长连接录像仍 BLOCKED） |
| R02 单页 Composer | V3-02/09 | 产品源是 `web/` TypeScript+Vite+Konva；`composer.html` 仅 fallback |
| R03 轻量白板 | V3-12/13 | 与标注共用 Konva 编辑器；桌面 Playwright 有白板+编号截图 |
| R04 先图后文、不发 Enter | V3-15 | 产品窗 CONFIRMED + 200 轮协议浸泡；Cursor 附件观察 BLOCKED_NATIVE |
| R05 召回且重核目标 | V3-16 | Intent 幂等 / 只补文字 / 换目标停止 |
| R06 同步不发键 | V3-04/06 | ping/hello 不唤醒；重连不 insert |
| R07 图片原子落盘 | V3-05/17 | SQLite + 1MiB 分块续传；magic + os.replace |
| R08 配对授权 | V3-04/10/19 | 截图可拒；区域截图 DPI e2e 已过 |
| R09 无 Key 可用 | V3-18 | BYOK skipped |
| R10 隔离日用数据 | V3-00/21 | `DT_V3_DATA_DIR` / preview-v3；日用切换未执行 |
| R11 隧道/新平台 | — | 明确后置，未实现 |

## 诚实状态

- 自动测试：`python -m pytest -q`（66 passed）。
- 验收表：`docs/pocket-composer-v3/fixtures/acceptance.json` 已按证据填写，不是全 PASS。
- HTML 设计原型不是产品 PASS。
- 真机豆包输入法、Cursor Composer 附件观测、独立复核、日用切换：BLOCKED_NATIVE / 未执行。
- 本文件随候选提交，不构成发版授权。
