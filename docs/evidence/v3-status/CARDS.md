# V3 24 卡诚实状态（隔离分支，未 merge / 未 Release）

统计来自 `fixtures/acceptance.json`（独立复核 9dd3a369 R0 更正后）：PASS 24 / BLOCKED_NATIVE 28 / NOT_RUN 44 / FAIL 0。

旧“PASS 50”作废。源码存在、脚本返回 0、文件存在都不算产品验收。

| 卡 | 做了什么 | 验收 |
|---|---|---|
| V3-00 | 基线 SHA/隔离数据已有证据 | 001/003/004 PASS；002 无真机 IME → BLOCKED |
| V3-01 | 产品窗先图后文；Cursor UIA 未闭合 | 005/007 NOT_RUN（旧证据范围不足）；006/008 BLOCKED |
| V3-02 | 无 adb | 009–011 BLOCKED；012 NOT_RUN |
| V3-03 | 冻结/版本单测 | 部分 PASS；冲突/往返 NOT_RUN |
| V3-04 | 配对/授权：挑战桌面发放、POST 不能自授 | 017/019/020 COMPONENT PASS；过期/撤销续发 NOT_RUN |
| V3-05 | SQLite + 分块续传 | 资产单测 PASS；1MiB 边界仍属 R2 |
| V3-06 | 协议 ACK/不注入 | 025/026/028 NOT_RUN；027 PASS |
| V3-07 | HUD 空闲隐藏单测 | 029/030/032 NOT_RUN（无网络线程原生窗） |
| V3-08 | 热键连按/锁屏未做专项 | 033–036 NOT_RUN |
| V3-09 | Vite+Konva 产品页 | 039 NOT_RUN；037/038/040 真机 BLOCKED |
| V3-10 | 区域截图单测 | 044 有范围 PASS；041 无手机 BLOCKED |
| V3-11/12/13/14 | 画布代码；真机触控没有 | 多数 BLOCKED/NOT_RUN |
| V3-15 | 产品窗顺序投递 | 062/064 PASS；061/063 NOT_RUN（不是 Cursor / 同类目标） |
| V3-16 | 换目标/恢复 | 065–067 NOT_RUN；068 PASS |
| V3-17 | SQLite 历史 | 069–071 PASS；072 NOT_RUN |
| V3-18 | 无 Key 跳过单测 | 074/076 NOT_RUN；真机完整链路 BLOCKED |
| V3-19 | 热键迁移文档 | 078/079 NOT_RUN |
| V3-20 | 本地 onedir 统计 | 084 缩范围 PASS；081/083 缺真机 BLOCKED |
| V3-21 | workflow 已列 Pillow；本 SHA 云端未跑绿 | 085/088 NOT_RUN |
| V3-22/23 | 独立复核 REQUEST_CHANGES；日用切换未执行 | 091/093 BLOCKED/NOT_RUN；096 PASS（明确没发版） |
