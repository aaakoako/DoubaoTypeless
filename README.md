# DoubaoTypeless

同 WiFi 下用手机页语音输入，文本同步到 Windows，审阅后插入当前光标。可选 **OpenAI 兼容** API 做前台纠错与后台学习（BYOK）。**非官方**社区工具，与字节跳动及「豆包」产品无关联。

<img width="422" height="308" alt="image" src="https://github.com/user-attachments/assets/d5156926-680d-4bb4-8460-558bbdca60d0" />

## 为什么做这个

1. **少打字、多语音**：思路在脑子里时直接说，减少长句手敲打断。  
2. **BYOK**：纠错 / 学习用你自己的 API，模型与上下文自己控。  
3. **手机语音接到 PC 焦点**：局域网网页把语音接到当前输入框，写代码、填聊天框都方便。  
4. **豆包输入法（Android）语音好用**：在手机上用习惯的输入法说完，同步到 Windows 继续编辑；本工具**不依赖**官方客户端，只是兼容这一常见输入路径。

## 和 Vibe Coding

光标停在 IDE 聊天、Composer、终端、注释等处：手机说完 → PC 小窗确认 → 插入。可选前台纠错、后台从审阅里学专名口癖。仓库提供的是 **HTTP + WebSocket 桥接 + 审阅窗口**，不是 IDE 插件。

## 环境 / 启动

- **Windows**，**Python 3.11+**，项目根目录：`pip install -r requirements.txt` → `python main.py`（或 `scripts/启动.bat`）。
- 首次运行生成 **`config.json`**。托盘 **设置** 里看手机访问地址或扫码（须同一 WiFi）。
- 默认数据在 **`data/`**，字段示例见 **`config.json.example`**。不配 API 也能完成桥接与插入；纠错/学习在设置里填 Base URL、Key、Model。
- 厂商预设见 **`providers.json`**（含推荐 **temperature**，留空时默认 **0.3**）。统一多模型可走 [LiteLLM](https://github.com/BerriAI/litellm) 等代理，把 Base URL 指过去即可。
- **勿**提交含真实密钥的 `config.json`（见 `.gitignore`）。
<img width="450" height="600" alt="image" src="https://github.com/user-attachments/assets/370eb079-7229-4b51-8b0f-e3bc7d6ce90f" />

## Windows 说明

- 可选开机自启（注册表 Run）；打包 exe 无控制台时日志在 **`debug.log`**（与 exe 同目录），设置或托盘可开日志窗口。需要记录正文级日志时：`set DT_VERBOSE_LOG=1` 后启动（PowerShell：`$env:DT_VERBOSE_LOG=1`）。
- 检测局域网 IP 时会向 `8.8.8.8:80` 做 UDP connect（不写业务内容）。

### 应用内更新与 Release 附件

- **单文件 exe 自动更新**：从 Release 下载新版本到同目录后，程序会退出并由隐藏批处理等待进程结束、删除旧 exe、改名新文件并重启。若杀软/同步盘/文件占用导致替换失败，界面可能已关闭但版本未变；请查看同目录下的 **`update.log`** 与 **`debug.log`**（带 `[update]` 时间戳）。失败时可能保留 **`_DoubaoTypeless_update_failed.bat`**，便于对照日志排查。
- **更稳妥的方式**：同一 Release 通常还提供 **`DoubaoTypeless_win_portable.zip`**（onedir 便携目录）。请先**完全退出**程序与托盘，解压 zip，用其中的 **`DoubaoTypeless` 文件夹整包覆盖**你正在使用的目录（或只覆盖该文件夹内文件），再启动 exe。这样不依赖「运行中自删 exe」，适合自动更新不稳定的环境。
- 本地打包：单文件 `pyinstaller --noconfirm DoubaoTypeless.spec`；便携目录 `pyinstaller --noconfirm DoubaoTypeless_portable.spec`，再将 `dist/DoubaoTypeless` 打成 zip 即可。

## 许可证

应用代码 **MIT**（[LICENSE](LICENSE)）。运行依赖及许可证以 **`requirements.txt`** 与各包声明为准（含 LGPL 等，分发前请自行评估）。

## 声明

个人/社区工具；「豆包」为相关权利人商标，仅说明输入法使用场景。
