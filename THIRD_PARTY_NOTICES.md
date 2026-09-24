# Third-party notices / 第三方声明

Pocket Composer source and original documentation are MIT licensed. Dependencies keep their own licenses; MIT is not a replacement license for them.

Pocket Composer 源码及原创文档采用 MIT。第三方组件保留各自许可证，不能把整个安装目录笼统视为 MIT。

| Component / 组件 | Purpose / 用途 | License family / 许可 |
|---|---|---|
| Python | Runtime / 运行时 | Python Software Foundation and included notices |
| PyInstaller bootloader | Frozen executable / 可执行文件加载器 | GPL with the upstream distribution exception; see shipped COPYING |
| Qt, PySide6, Shiboken | Windows UI / 桌面界面 | Open-source LGPLv3 option for included runtime modules; component notices also apply |
| pynput | Input integration / 输入集成 | LGPLv3 |
| Pillow | Image processing / 图像处理 | MIT-CMU and bundled image-library notices |
| aiohttp | Phone bridge / 手机桥接 | Apache-2.0 AND MIT |
| httpx, qrcode | API transport, pairing / API与配对 | BSD-family notices |
| comtypes | Windows UI Automation | MIT |
| pywin32 | Windows integration / 系统集成 | Upstream PSF-style notices; see shipped files |
| Konva | Phone annotation canvas / 手机标注 | MIT |

The build writes an exact dependency inventory and copies available upstream license/notice files to `_internal/licenses/components.json` and `_internal/licenses/`. Versions in that file describe that particular build, not every release. Transitive dependencies and image codecs have additional notices in that directory.

构建会把实际识别出的依赖版本、来源和许可证文件写入 `_internal/licenses/components.json` 及同目录。清单对应具体构建；传递依赖和图像编解码库仍有各自声明。

## LGPL libraries / LGPL库

The shipped application uses separate, dynamically loaded libraries. Keep the LGPL/GPL texts and copyright notices when redistributing them. Users may replace compatible LGPL libraries and debug modifications to those libraries; this project imposes no additional restriction on that activity. A library replacement is not covered by the original package hash or the project's compatibility testing.

随包库以独立文件动态加载。再分发时保留 LGPL/GPL 文本及版权声明。用户可以替换兼容的 LGPL 库并调试这些库的修改；本项目不另行限制。替换后的库不再对应原安装包校验值或既有兼容性验证。

Quit the app and work on a copy of the portable folder. Qt libraries/plugins are in `_internal/PySide6`, Shiboken in `_internal/shiboken6`. Replace a matching version/architecture as a complete compatible set. For packaged Python modules such as pynput, rebuild from this repository with the modified dependency (`docs/release/v3-build.md`); the app's MIT source and PyInstaller build recipe remain available. Do not remove or modify the user's draft directory.

先退出应用，在便携目录副本上操作。Qt库/插件位于 `_internal/PySide6`，Shiboken位于 `_internal/shiboken6`；使用匹配架构的兼容库组合替换。pynput等已打包Python模块可按构建指南安装修改版依赖后重新打包。不要删除或修改用户草稿目录。

Source references / 对应源码入口:
- Qt: https://download.qt.io/official_releases/qt/ — use the version recorded in components.json; Qt Base, SVG and Image Formats sources cover the included Qt runtime/plugin families.
- Qt for Python: https://code.qt.io/cgit/pyside/pyside-setup.git/ — matching PySide6 version tag.
- pynput: https://github.com/moses-palmer/pynput — matching recorded release; source archives are also listed on PyPI.
- Other Python dependencies: exact-version source indexes appear in components.json.
- Konva: https://github.com/konvajs/konva

The Windows build excludes the unused Qt Virtual Keyboard plugin (GPL/commercial) and unused PDF/QML/Quick runtime modules. It uses the Windows/phone system input methods; excluding Qt Virtual Keyboard does not disable those input methods. Microsoft runtime libraries retain Microsoft's terms. Model providers, trademarks and service credits are not licensed by this project's MIT license.

Windows构建排除未使用的 Qt Virtual Keyboard（GPL/商业许可）和PDF/QML/Quick运行库；用户仍使用Windows或手机系统输入法。Microsoft运行库适用其自身条款。模型服务、商标和API额度不属于本项目MIT授权。

Official references / 官方依据: [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations), [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html), [Qt Virtual Keyboard licensing](https://doc.qt.io/qt-6/qtvirtualkeyboard-index.html).
