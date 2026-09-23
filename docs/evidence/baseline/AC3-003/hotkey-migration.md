# 旧 Alt+Shift+I 语义 → v3 迁移

审查基线 `e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5` 源码事实：

- `gui.py` ReviewWindow 绑定 `<Alt-Shift-I>` / `<Alt-Shift-i>` 到 `_skip_llm_insert()`。
- 按钮文案为「跳过纠错并插入」。该动作把当前审阅框正文作为 `final_text`，并带 `skip_llm=True` 调用插入。
- 全局热键服务 `hotkeys.build_bindings` **只注册两个动作**：唤起审阅（默认 `<ctrl>+<shift>+u`）和插入并复制（默认 `<alt>+i`）。Alt+Shift+I **不是**全局空闲热键，只在审阅窗口自身有焦点时生效。
- 设置页插入热键输入框的 placeholder 误写为 `<alt>+<shift>+i`，与默认值 `<alt>+i` 不一致；迁移时不得把这个 placeholder 当成已注册全局键。

v3 决定（`spec/00`、`spec/03`、`spec/09`）：

- 新版本 Alt+Shift+I 用于**召回上次不可变图文并按当前目标重试**，不再表示「跳过纠错」。
- 设置迁移必须说明旧语义，并删除旧绑定，**不能双重执行**（既跳过纠错又召回重试）。
- 无 Key 的旧文字路径不依赖该键；V3-00 只记录事实，不改稳定热键。
