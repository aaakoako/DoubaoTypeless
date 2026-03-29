# DoubaoTypeless

同 WiFi 下用手机浏览器打开本机页面，通过手机输入法语音输入，文本同步到 Windows，在审阅窗口确认后插入当前光标处。可选兼容 OpenAI 协议的 API 做前台纠错建议与后台学习（BYOK）。**非官方**社区工具，与字节跳动及「豆包」产品无关联。

---

## 为什么做这个

1. **写代码时少打字、多语音**  
   思路在脑子里时直接说，减少长句手敲打断，和 vibe coding 更合拍。

2. **Bring Your Own Key**  
   纠错 / 学习走你自己申请的 API，模型与上下文自己控。

3. **手机语音接到 PC 焦点**  
   用局域网网页把手机语音接到 PC 当前输入焦点，服务在电脑上写代码、填聊天框等场景。

---

## 和 Vibe Coding

光标停在 **IDE 聊天、Composer、终端、注释** 等处：手机说完 → PC 小窗确认 → 插入。可选前台 LLM 纠错、后台从审阅里学习专名口癖。  
本仓库是 **HTTP + WebSocket 桥接 + 审阅窗口**，不是 IDE 插件。

---

## 开箱即用

环境：**Python 3.11+**；依赖含 **`pywin32`**，请在 **Windows** 上安装（托盘、全局热键与粘贴链路仅在该环境验证）。

从本仓库克隆或解压后，在**项目根目录**：

1. `pip install -r requirements.txt`
2. `python main.py`（首次运行会在根目录自动生成 **`config.json`**，默认即可跑通「语音 → 审阅 → 插入」）
3. 托盘 → **设置** 里查看「当前访问地址」或扫码（**手机与电脑同一 WiFi**），在手机页用输入法语音输入即可同步到 PC。

Windows 可双击 **`scripts/启动.bat`**（等价于在项目根目录启动 `main.py`）。

默认数据在 **`data/`**（已带示例 **`data/dictionary.txt`**；审阅历史、学习样本等路径可在设置里改，与 **`config.json.example`** 字段说明一致）。**前台纠错 / 后台学习**需在设置里填写 Base URL、Key、Model 后开启；**不配 API 也能完成桥接与插入**。

**多厂商 OpenAI 兼容**：设置里 **Provider** 下拉与仓库内 **`providers.json`**（url / models / 推荐 **temperature**）对齐常见写法，与 [Open WebUI](https://github.com/open-webui/open-webui) 等工具的「厂商预设」同类。需要**一条网关统一多模型**时，可自建 [LiteLLM Proxy](https://github.com/BerriAI/litellm)，把 Base URL 指到代理即可，无需改本程序代码。

**MiniMax**：Base **`https://api.minimaxi.com/v1`**（[文档](https://platform.minimaxi.com/docs/api-reference/text-openai-api)）；漏写 **`/v1`** 时会自动补全。兼容层要求 **temperature ∈ (0, 1]**；配置留空时程序按网关自动选（MiniMax 默认 `0.01`），也可在 **设置 → 高级** 里分别填前台/后台 **temperature**。会按需加 **`reasoning_split`** 以便读正文。

若曾使用旧版、在仓库**根目录**还留有 `review_history.json` / `learn_pending.json`，而配置已指向 `data/`，可删除根目录这两份以免混淆（见 `.gitignore`）。

**勿**将含真实密钥的 `config.json` 提交公开仓库（见 `.gitignore`）。

### 应用选项（Windows）

- **开机自动启动**：写入当前用户注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`；打包 exe 时指向该 exe，源码运行时优先使用同目录下的 `pythonw.exe`。
- **调试日志**：默认**不弹出控制台窗口**（打包为 `console=False` 的单文件 exe）。日志写入 **`debug.log`**（与 `config.json` 同目录）。可在 **设置** 或托盘菜单打开 **调试日志** 窗口查看尾部内容；需要更详细正文日志时可设环境变量 `DT_VERBOSE_LOG=1`（见下）。

## 运行

```bash
python main.py
```

检测本机局域网 IP 时会向 `8.8.8.8:80` 发起 UDP connect（常见写法，不传输业务正文）。

## 隐私与日志（默认）

默认 **`debug.log` 不写**同步与纠错的正文片段，只记长度与状态。排查时可临时：

```bash
set DT_VERBOSE_LOG=1
python main.py
```

PowerShell：`$env:DT_VERBOSE_LOG=1; python main.py`

## 第三方依赖与许可证（简述）

本项目 **应用层代码** 以 **MIT** 发布（见仓库根目录 **`LICENSE`**）。运行依赖包括但不限于（以 `requirements.txt` 为准）：

| 依赖 | 常见许可证（以各包官方声明为准） |
|------|----------------------------------|
| customtkinter | MIT |
| httpx | BSD-3-Clause |
| aiohttp | Apache-2.0 |
| Pillow | HPND |
| pynput | LGPL-3.0 |
| pystray | LGPL-3.0 |
| pywin32 | PSF / 包内许可 |
| qrcode | BSD |

使用前请阅读各依赖的官方许可证文本；若对 LGPL 等有合规要求，请自行评估分发方式（例如是否与 PyInstaller 单文件捆绑符合你的场景）。

## 声明

本项目为个人/社区工具，**与字节跳动及「豆包」官方产品无关联**；「豆包」为相关权利人商标，仅用于说明兼容的输入法使用场景。

## License

[MIT](LICENSE)
