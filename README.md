# DoubaoTypeless

同 WiFi 下用手机页语音输入，文本同步到 Windows，审阅后插入当前光标。可选 **OpenAI 兼容** API 做前台纠错与后台学习（BYOK）。**非官方**社区工具，与字节跳动及「豆包」产品无关联。

## 环境 / 启动

- **Windows**，**Python 3.11+**，项目根目录：`pip install -r requirements.txt` → `python main.py`（或 `scripts/启动.bat`）。
- 首次运行生成 **`config.json`**。托盘 **设置** 里看手机访问地址或扫码（须同一 WiFi）。
- 默认数据在 **`data/`**，字段示例见 **`config.json.example`**。不配 API 也能完成桥接与插入；纠错/学习在设置里填 Base URL、Key、Model。
- 厂商预设见 **`providers.json`**（含推荐 **temperature**，留空时默认 **0.3**）。统一多模型可走 [LiteLLM](https://github.com/BerriAI/litellm) 等代理，把 Base URL 指过去即可。
- **勿**提交含真实密钥的 `config.json`（见 `.gitignore`）。

## Windows 说明

- 可选开机自启（注册表 Run）；打包 exe 无控制台时日志在 **`debug.log`**（与配置同目录），设置或托盘可开日志窗口。
- 需要记录正文级日志时：`set DT_VERBOSE_LOG=1` 后启动（PowerShell：`$env:DT_VERBOSE_LOG=1`）。
- 检测局域网 IP 时会向 `8.8.8.8:80` 做 UDP connect（不写业务内容）。

## 许可证

应用代码 **MIT**（[LICENSE](LICENSE)）。运行依赖及许可证以 **`requirements.txt`** 与各包声明为准（含 LGPL 等，分发前请自行评估）。

## 声明

个人/社区工具；「豆包」为相关权利人商标，仅说明输入法使用场景。
