# 9dd3a369 独立复核后的 PASS 更正

复核固定提交：`9dd3a369f1b566d0fdc548cee3af934523e9b8db`  
本批只做证据校正（R0）与授权隔离（R1）。旧证据文件保留，只改适用范围。

| 用例 | 原标 | 现标 | 原因 |
|---|---|---|---|
| AC3-025 | PASS | NOT_RUN | ACK 恒 durable=True，未证明落盘/阻断语义 |
| AC3-030 | PASS | NOT_RUN | 产品窗截图不能证明网络线程原生 HUD 生命周期 |
| AC3-052 | PASS | NOT_RUN | 仅有 canvas.ts，未跑 50 步撤销 |
| AC3-057 | PASS | NOT_RUN | 无导出像素独立验证 |
| AC3-063 | PASS | NOT_RUN | 现有单测只换窗口分类，不是同类 Composer 不同 HWND |
| AC3-065 | PASS | NOT_RUN | 召回路径未在错焦点后原生重试 |
| AC3-066 | PASS | NOT_RUN | 仅 policy 函数，未做只补文字召回 |
| AC3-067 | PASS | NOT_RUN | 仅证明不发 Ctrl+A；ask UI 未原生验收 |
| AC3-072 | PASS | NOT_RUN | 凭据库失败/诊断包未执行 |
| AC3-074 | PASS | NOT_RUN | 无 Key/拒图 ≠ 401/404/429/超时/TLS |
| AC3-076 | PASS | NOT_RUN | 调用前过期 revision，未覆盖 post 期间改稿 |
| AC3-079 | PASS | NOT_RUN | 监听启动成功不是占键检测 |
| AC3-084 | PASS | PASS（缩范围） | 仅本地 onedir 统计，不是 Release 产物 |

`tools/v3_fill_acceptance.py` 设置 `REFUSE_PASS_MINT`：不得把未 PASS 的用例写成 PASS。
