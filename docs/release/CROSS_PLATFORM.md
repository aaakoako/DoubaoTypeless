# macOS 与 Linux 体验版 / Cross-platform preview

Pocket Composer 将手机上的文字、图片和白板同步到电脑，再插入您选中的输入框。
此版本为跨平台体验版，不取代 Windows 正式版。模型分析可选，默认关闭。

## macOS

- 下载与芯片对应的 DMG，将 **Pocket Composer** 拖到 **Applications**。
- 首次启动需要在系统设置 → 隐私与安全性中允许应用运行。本体验包尚未取得 Apple Developer ID 签名和公证；请核对本仓库发布的 SHA256，不要关闭系统全局安全检查。
- 自动插入需要授予 **辅助功能** 权限；全局快捷键可能还需要 **输入监控** 权限，授权后重新启动。截屏需要 **屏幕录制** 权限。
- 先点击目标输入框，再从手机插入。图片后接文字使用 Command+V。目标未暴露可编辑控件或插图后焦点改变时，会保留稿件供恢复，不猜测其他输入框。
- API Key 存入 macOS 钥匙串；无法访问钥匙串时仅在本次运行中保留。

## Linux

- 面向 Ubuntu 22.04 及更新系统、x64、**X11 桌面会话**。下载 `.deb` 后用软件安装器打开，或执行 `sudo apt install ./PocketComposer_*_linux_x64.deb`。
- 也可解压 `.tar.gz`，运行 `PocketComposer/PocketComposer`；系统需要 Qt X11 运行库、`libatspi2.0-0` 和 `at-spi2-core`（依赖列表见 DEB）。
- 开启桌面辅助功能。部分 Electron 应用需自行启用无障碍支持，才能识别其输入框。无法识别时不会盲目向终端或其他窗口插入。
- Wayland 当前可编辑、同步、复制，尚不支持自动插入、全局快捷键及截屏；需要这些功能请登录 X11 会话。
- API Key 存入系统 Secret Service（例如 GNOME Keyring）；没有可用密钥环时仅保留到退出。

## 更新与验证边界

关闭应用后，用新包替换应用本体；不会下载或执行 Windows 升级程序。数据独立保存于用户目录的 `DoubaoTypeless/workspace-v3`（历史内部目录名保留）。不要删除数据目录来升级。

此体验版尚未提供 macOS/Linux 登录自启动；设置中的对应选项已禁用。

构建启动、桌面图文粘贴和真实 Codex/Cursor 接收属于不同验证项。请以对应发布页列出的实测结果为准；未实测的平台、输入框和多屏行为不宣称完成验收。

## English

This is an experimental macOS/Linux build of Pocket Composer, not a replacement for the stable Windows release. Optional model analysis is off by default.

**macOS:** choose the DMG for your CPU and drag the app to Applications. The preview is not Developer ID signed or notarized. Verify the published checksum and use the per-app Privacy & Security approval; do not disable system-wide protection. Grant Accessibility for insertion, Input Monitoring if requested for shortcuts, and Screen Recording for capture. Restart after granting permissions. Select the destination input first. Images and text use Command+V; changed or inaccessible targets stop safely with the draft retained. Keys use the macOS Keychain, falling back to memory only when unavailable.

**Linux:** Ubuntu 22.04+ x64, X11. Install the DEB with your software installer or `sudo apt install ./PocketComposer_*_linux_x64.deb`. The tarball needs the system libraries listed in the DEB dependencies, including AT-SPI2 and Qt X11 libraries. Enable desktop accessibility; some Electron apps also require accessibility support enabled. Wayland currently supports editing, sync and copy, but not automatic insertion, global shortcuts or capture. API keys use Secret Service; without a working keyring they remain in memory only.

**Updates:** quit and replace the application using the matching OS package. Keep the user data directory `~/DoubaoTypeless/workspace-v3`; the historical internal name is intentional. macOS/Linux never run the Windows updater. Frozen startup, native paste tests and real Codex/Cursor acceptance are separate checks: see each release's evidence and limitations.

Login autostart is not yet available on macOS/Linux; its setting is disabled in this preview.
