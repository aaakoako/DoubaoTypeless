# V3 24 卡诚实状态（隔离分支，未 merge / 未 Release）

统计来自 `fixtures/acceptance.json`：PASS 50 / BLOCKED_NATIVE 27 / NOT_RUN 19 / FAIL 0。

| 卡 | 做了什么 | 验收 |
|---|---|---|
| V3-00 | 基线 SHA/隔离数据已有证据 | 001/003/004 PASS；002 无真机 IME → BLOCKED |
| V3-01 | 产品窗先图后文；Cursor UIA 未闭合 | 005/007 PASS；006/008 BLOCKED |
| V3-02 | 无 adb | 009–011 BLOCKED；012 资源 PASS |
| V3-03 | 冻结/版本单测 | PASS |
| V3-04 | 配对/授权单测 | PASS |
| V3-05 | SQLite + 1MiB 分块续传 | PASS |
| V3-06 | 协议 ACK/不注入 | 025/026/028 PASS；027 NOT_RUN |
| V3-07 | HUD 空闲隐藏；10min RSS 采样 | 029/030/032 PASS；081 无真机连接 BLOCKED |
| V3-08 | 热键连按/锁屏未做专项 | 033–036 NOT_RUN |
| V3-09 | Vite+Konva 产品页；桌面 360/390/430 | 039 PASS；037/038/040 真机 BLOCKED |
| V3-10 | 区域截图+DPR=2 e2e；取消不落盘 | 042–044 PASS；041 无手机 BLOCKED |
| V3-11/12/13/14 | 画布代码+Playwright 编号；真机触控没有 | 多数 BLOCKED；059 桌面编号 PASS |
| V3-15 | 产品窗顺序投递 + 200 轮协议浸泡 | 061–064 PASS（目标不是 Cursor） |
| V3-16 | 换目标停止/幂等 | 部分 PASS；错焦点重试 UI NOT_RUN |
| V3-17 | SQLite 历史 | PASS |
| V3-18 | 无 Key BYOK | 自动 PASS；真机完整链路 BLOCKED |
| V3-19 | 热键迁移文档 | 部分 PASS |
| V3-20 | 200 轮协议过；10min HUD 隐藏；onedir 本地包 | 083/081 缺真机 BLOCKED；084 本地包 PASS |
| V3-21 | 本地 onedir，没有 CI runner | 085/088 NOT_RUN |
| V3-22/23 | 独立复核不能自签；日用切换未执行 | 091/093 BLOCKED/NOT_RUN；096 PASS（明确没发版） |
