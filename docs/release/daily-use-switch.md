# 日用切换（未执行）

这是候选切换说明，**本轮没有把日用入口切到 V3，也没有 merge / Release**。

## 若以后要切

1. 保留现有 `python main.py` / 已安装 exe 和 `config.json`、`data/`。
2. V3 只用 `%LOCALAPPDATA%\DoubaoTypeless\preview-v3` 或 `DT_V3_DATA_DIR`。
3. 不要把 preview 目录拷进日用 `data/`。
4. 回退：继续跑原来的 `main.py`。

## 本轮状态

- 未修改稳定分支
- 未打 v* tag
- 未创建 GitHub Release
- 未覆盖仓库 `config.json`
