# 隔离无控制台包 · 原生窗口 / 长文像素

不是 RELEASE_READY。真机 Android+豆包与真实 Cursor 仍只阻塞对应验证。

## 包

- 入口：`docs/evidence/v3-s5-pack/dist/DoubaoTypelessV3PreviewUI/DoubaoTypelessV3PreviewUI.exe`
- EXE SHA256：`4bae6609e4b5af5e6c8508b774bb7b023b4c0462dd43625e95f96ee9617ae00f`
- ZIP SHA256：`f23be749dbc35c89e7e8f5a909c1f041ac33e0ffbd48ed691262336d853181df`
- 管道：`DoubaoTypelessV3Preview-native-pixels`
- 数据目录：本目录 `smoke-data/`（已忽略，不进日用 `config.json`）

## 第一次用旧包 `fe74c425…`

`first-fail.json`：长文 904 字进了 HUD，宽 400，但 QTextEdit 最小高度把底栏挤出窗外，`插入并复制` 不在像素里。没有放宽断言。

## 修复后再打的包 `4bae6609…`

`result.json` 与 `hud.png` / `client.png`：

- HUD 400×300，正文完整可滚，不是尾部 200 字
- 底栏可见：展开 / 复制 / **插入并复制**
- 连接窗口有页签、配对地址、权限行
- `android_claimed=false`，`cursor_claimed=false`，`release_ready=false`

核对脚本：`tools/v3_native_pack_pixels.py`。只对该隔离管道发 `--quit`。
