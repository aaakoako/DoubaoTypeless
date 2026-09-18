# 09 · 基线证据、选型决定和事实边界

## 1. 再次核查

2026-09-18通过GitHub connector查询master，返回SHA仍为`e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5`，提交描述Release v0.4.2 diagnostics and updater fixes。本轮进一步读取hotkeys.py及gui.py 230–430；其余基线事实来自同一提交在本对话已实际读取的源码。没有对所有文件重新跑测试。容器直接网络下载源码失败，因此不假装本地克隆或源码测试已经完成。

## 2. 源码事实到改动的映射

| 证据位置（固定SHA） | 源码事实 | v3改动/仍需验证 |
|---|---|---|
| gui.py 230–430，ReviewWindow::show_recording | 当前窗最小460×360；show_recording里focus_force；既有跳过纠错/清空/历史/建议区 | 改为360×88/132按需HUD，非激活；实际输入法/焦点效果需Windows验证 |
| 同段gui.py局部快捷键 | Alt+Shift+I当前用于跳过纠错，不是新空闲键位 | 新版本用于召回重试，设置迁移需说明且删除旧绑定，不能双重执行 |
| hotkeys.py | pynput监听，文档明确不能检测全部外部占用；build_bindings只两个动作 | 新平台HotkeyService增加截图/召回；反馈真实注册结果，不夸大冲突探测 |
| main.py::_process_bridge_text / _do_insert | pending共享文字、await建议、粘贴后通知清空 | 新Draft/Bundle/Attempt分离、AI旁路、精确归档 |
| bridge.py::_handle_ws / notify_cleared | 文本消息协议，无逐版本Bundle与资产；清空广播无稿件身份 | v3鉴权+明确ACK+二进制图片+来源隔离 |
| phone.html::autoSync / sendNow / onmessage | 发送后即标synced、cleared直接清空当前输入 | 服务端ACK和版本归档；手机编辑器共用草稿 |
| typer.py::paste_text | Windows文字剪贴板、恢复窗口、Ctrl+V；paste_sent是发键结果 | 真正图像格式、适配器、步进观察和部分恢复 |
| config.py::Config/save | Key以普通JSON字段保存，前台/后台两套模型 | 凭据库、单手动BYOK，旧学习只归档 |
| release.yml | v*标签触发Windows构建和Release | 新preview artifact与测试门槛，禁止本轮直接发布稳定 |

- 固定源码：[gui.py](https://github.com/aaakoako/DoubaoTypeless/blob/e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5/gui.py)
- 固定源码：[hotkeys.py](https://github.com/aaakoako/DoubaoTypeless/blob/e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5/hotkeys.py)
- 固定源码：[main.py](https://github.com/aaakoako/DoubaoTypeless/blob/e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5/main.py)
- 固定源码：[bridge.py](https://github.com/aaakoako/DoubaoTypeless/blob/e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5/bridge.py)
- 固定源码：[phone.html](https://github.com/aaakoako/DoubaoTypeless/blob/e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5/phone.html)
- 固定源码：[typer.py](https://github.com/aaakoako/DoubaoTypeless/blob/e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5/typer.py)
- 固定源码：[config.py](https://github.com/aaakoako/DoubaoTypeless/blob/e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5/config.py)
- 固定源码：[.github/workflows/release.yml](https://github.com/aaakoako/DoubaoTypeless/blob/e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5/.github/workflows/release.yml)

## 3. 明确的未验证事项

没有真实Windows/手机/Cursor运行链路；没有检查用户已安装的Cursor版本和模型；没有真实API Key调用；不能承诺某个具体Composer的UIA附件状态可读。当前Cursor官方文档页面读取失败，因此本方案不引用它来声称一键图文兼容已成立。首张原生卡必须给出真实版本证据。

浏览器设计原型只能说明界面和部分本地编辑交互。截电脑/鉴权/远端同步/OS粘贴/加密存储在原型中均为模拟，详见原型说明和交付状态。

## 4. 官方技术参考（2026-09-18读取）

### [S01] Windows SetForegroundWindow

系统会限制前台激活，成功不能仅由HWND存在推出。

https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow

### [S02] Windows SendInput

事件注入数、UIPI、已按下修饰键会影响结果。

https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput

### [S03] MDN Pointer Events

触摸/笔/鼠标统一事件、pointer capture、cancel、pressure。

https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events

### [S04] MDN VisualViewport

布局视口与可见视口、软键盘对可见区域的影响。

https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport

### [S05] MDN getDisplayMedia

本设备屏幕捕获、安全上下文和用户动作边界；不是远程截电脑API。

https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia

### [S06] MDN Service Worker

安全上下文要求；普通手机LAN HTTP不能当完整离线PWA承诺。

https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API

### [S07] Qt QClipboard

Qt跨平台图像/文字剪贴板接口，不等于目标应用确认。

https://doc.qt.io/qt-6/qclipboard.html

### [S08] Windows Clipboard Formats

CF_DIB/CF_DIBV5等原生格式。

https://learn.microsoft.com/en-us/windows/win32/dataxchg/standard-clipboard-formats

### [S09] Qt QWidget / Qt枚举

Widgets窗口基础；非激活标志需Windows实际验证。

https://doc.qt.io/qt-6/qwidget.html

### [S10] Konva Free Drawing

以向量对象保存笔画、可选择/移动，或栅格绘制两种路径。

https://konvajs.org/docs/sandbox/Free_Drawing.html

### [S11] OWASP WebSocket Security

鉴权、Origin、WSS、限流/消息大小、日志脱敏。

https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html

### [S12] PyInstaller Manual

原生平台构建要求，不是交叉编译器。

https://pyinstaller.org/en/stable/

### [S13] Qt QScreen

屏幕/DPI/图像捕获接口，需物理像素验证。

https://doc.qt.io/qt-6/qscreen.html

### [S14] Konva Multi-touch

多指缩放示例不替代完整手势冲突处理。

https://konvajs.org/docs/sandbox/Multi-touch_Scale_Stage.html

## 5. 选型决定记录

ADR-01：保留Python核心，不全量换语言。桌面Widgets轻表面，手机才承担画布；收益是职责清晰、减少栈，代价是两种UI测试与Qt依赖体积，G0实测决定是否扩大。

ADR-02：有限画布+可编辑对象，非整张位图不可逆涂改；支持修订和清晰导出，代价是坐标/撤销/多指要认真实现。

ADR-03：桌面热键是最低摩擦且最明确的目标授权；手机按钮有验证门槛，不自动抢最近窗口。避免把“无感”解释为允许向任何前台界面注入。

ADR-04：不承诺任意Agent一键图文。先做用户最常用Cursor版本验证，再按适配器扩展；泛化失败不危害文字链路。

ADR-05：暂不引入隧道/协同/无限白板。安全配对与恢复是当前图文功能本身的必要基础，不能后置。
