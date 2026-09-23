# 迁移与回退

## 隔离

- 预览数据：`%LOCALAPPDATA%\DoubaoTypeless\preview-v3` 或 `DT_V3_DATA_DIR`。
- 预览管道 / 自启动名：`DoubaoTypelessV3Preview`，不会写日用 `DoubaoTypeless` Run 项。
- BYOK 密钥不进 `settings.json`。

## 只读导入

设置页「导入日用词库」从日用 `dictionary.txt` 复制到预览 `vocabulary.txt`。源文件字节不变，不写日用 `config.json`。

日用热键/学习开关可用 `inspect_legacy_config` 只读查看，不回写。

## 回退

继续使用原来的日用入口（`python main.py` 或已安装日用包）。不要把 preview-v3 拷进日用目录。关掉预览自启动即可，日用启动项保持不动。

用户明确批准前，不把预览切成日用默认。
