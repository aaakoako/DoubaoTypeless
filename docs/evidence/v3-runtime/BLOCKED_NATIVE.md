# BLOCKED_NATIVE

实现已在隔离分支继续，下列项**执行过环境检查**后仍不能写成产品 PASS。

- 真实 Android 豆包输入法 composition / 语音：本机无 adb（`docs/evidence/v3-ime/result.json`）
- 真实 Cursor Composer 附件树观察：Cursor 窗口在，UIA ProgID 未注册，`observe_*` 仍为 unknown（`docs/evidence/v3-cursor/result.json`）。`V3ComposerTarget` 的 CONFIRMED 不能冒充 Cursor
- 360/390/430 真机键盘顶起 / 两指触控：只有桌面 Chromium Playwright（`docs/evidence/v3-web/`）
- 10 分钟真机长连接录像：idle 采样是本机进程 RSS/HUD，不是手机录像
- 200 轮真机语音+截屏：协议浸泡 200 轮已过（`docs/evidence/v3-soak/result.json`），真机矩阵没有
- 独立复核：不能自签（`docs/evidence/v3-review/INDEPENDENT_REVIEW.md`）
- 日用切换：未执行（`docs/release/daily-use-switch.md`）

明确不做：merge、v* tag、GitHub Release、覆盖日用 config.json。
设计原型 `docs/pocket-composer-v3/prototype/index.html` 不是产品。
