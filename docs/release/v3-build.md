# V3 Windows 构建与发布

版本权威是 `src/doubao_typeless/build_info.py::VERSION`，当前为 0.5.0。仓库默认分支仍是 `master`。根目录旧 Tk 打包配置与 `app_version.py` 属于 0.4.2 兼容代码，不作为 V3 发行入口。

在干净的固定提交上执行（Windows，Python 3.13、Node.js 22）：

```powershell
python -m pip install -r requirements-v3-release.txt -r requirements-test.txt playwright==1.60.0
python -m playwright install chromium
cd web
npm ci
npm run typecheck
npm run build
cd ..
python tools/export_ui_theme.py --check
python tools/export_v3_icon.py
# 如果生成的跟踪文件有变化，应核对并提交后继续。
python -m pytest -q
python tools/prepare_v3_release.py --channel release-candidate
python -m PyInstaller --noconfirm packaging/v3_release.spec
python tools/fetch_nsis.py G:/AgentStorage/Caches/typeless-nsis
python tools/package_v3_release.py dist/DoubaoTypeless --output release --compiler G:/AgentStorage/Caches/typeless-nsis/nsis-3.12/makensis.exe
```

安装器使用官方 [NSIS 3.12](https://nsis.sourceforge.io/Download)，工具链 ZIP 固定 SHA-256 后才解压，许可见 [NSIS License](https://nsis.sourceforge.io/License)。不用管理员权限，不强制结束用户进程，不修改旧版数据目录。

构建身份要求干净 Git 提交；打包时同时核对 payload、prepare 记录和 HEAD，并拒绝未提交源码。生成的证据仅允许位于独立 `evidence/`，不会被打入产品。ZIP 包含完整 onedir，附完整文件清单和安装包/ZIP 校验和。

CI 对 Windows/Linux 执行生产网页构建、全量测试和证据检查器自测。Release 工作流复用 CI，在隔离 Windows runner 运行实际冻结启动、三轮文字、手机主稿和三图投递，再生成安装器并验证安装、升级布局、真实 V3 数据保留、跨目录卸载保护及占用文件卸载重试。

安装测试使用独立注册命名空间，不改日用快捷方式和自启动。“旧版本”安装器只是目录布局替身，不能据此宣称真实 0.4.2 数据迁移通过。合成浏览器投递不能代替实际 Codex/Cursor，离屏手机测试不能代替真机输入法。

标签必须等于 `v` 加源码版本。推送标签后只创建 **draft Release**；固定提交的真实产品验收、兼容性记录和人工发布决定完成后，才能公开发布。普通分支手动运行仅上传候选产物。
