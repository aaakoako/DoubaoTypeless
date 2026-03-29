## Legacy Archive

这里归档的是已经退出主线的实验方案，避免继续和当前的 `手机网页桥接` 主链路混在一起。

当前主线：
- 手机浏览器打开本机页面
- 手机上使用豆包输入法语音输入
- 文本自动同步到 PC
- PC 审阅、LLM 建议、插入

已归档的旧方案：
- `legacy_pc_asr_notes.md`
  - 逆向 `doubaoime-asr`
  - PC 本地麦克风直录
  - `INTERIM_RESULT / FINAL_RESULT` 拼接实验
- `legacy_hotkey.py`
  - 旧直录链路使用的全局热键监听器

这些内容只保留作复盘和回滚参考，不再参与当前主线运行。

其它说明：
- `legacy_pc_asr/`：旧 PC 直录链路的 `opus.dll`、`credentials.json` 等备份；**当前程序不读取**，由 `.gitignore` 排除，勿提交。
- `scratch/`：临时挪出的测试/杂项，不参与运行。
- `test_snippets_legacy.txt` 等为历史测试片段。

根目录已整理：`data/` 存默认词典与运行期 JSON（见 `.gitignore`），`scripts/启动.bat` 供 Windows 启动。
