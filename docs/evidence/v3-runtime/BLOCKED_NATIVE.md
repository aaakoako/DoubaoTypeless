# BLOCKED_NATIVE

本轮在 `v3/00-baseline` 交付可运行的 Pocket Composer v3 运行时，但下列产品验收不能写成 PASS。

## 真机 / 原生

- 真实 Android 豆包输入法 composition / 语音：未接入测试机，Composer 页存在但不代替真机 IME。
- Cursor Composer 附件观察：适配器固定返回 `unknown`，粘贴成功不等于 CONFIRMED。
- 电脑截图授权后的端到端像素对照：单元层拒绝未授权/非法 scope，未做真屏截图像素比对。
- 360 / 390 / 430 CSS px 真机键盘顶起：仅静态检查 44px 触控区，无真机截图。
- 空闲 10 分钟无窗口、输入后 6 秒隐藏：HUD 默认隐藏有单测；未重录 Windows 生命周期录像。

## 明确不做

- 不合并 master，不打 v* tag，不发 GitHub Release。
- 不覆盖仓库 `config.json` / `data/` 日用数据；V3 写入 `%LOCALAPPDATA%\DoubaoTypeless\preview-v3` 或 `DT_V3_DATA_DIR`。
- HTML 设计原型 `docs/pocket-composer-v3/prototype/index.html` 不是产品 PASS。

## 可运行入口

```
scripts/启动-v3.bat
python -m doubao_typeless
```
