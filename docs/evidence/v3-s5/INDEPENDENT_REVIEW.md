# S5 独立复核包 — WAITING

实现者不能自签。本文件只列出必须由独立审阅者核对的材料。

## 范围

- S0 授权/隔离（已有独立复核 REQUEST_CHANGES 后的返修）
- S2 第一条真实图文链路
- S5 最终候选包、迁移/回退、发布边界

## 固定对象

- 实现切片 SHA：见 `docs/v3-delivery/CHECKPOINT.json` 的 `current_head`
- 包：`dist/DoubaoTypelessV3Preview/DoubaoTypelessV3Preview.exe`
- 哈希：`docs/release/checksums.txt`
- 不得用 HTML 原型、模拟 Cursor、或“源码存在”代替 PASS

## 必读证据

| 切片 | 路径 |
|---|---|
| S0 反例 | `docs/evidence/v3-review/counterexamples.json` |
| S1 文字 | `docs/evidence/v3-s1/` |
| S2 图文 | `docs/evidence/v3-s2/result.json` |
| S3 多图白板恢复 | `docs/evidence/v3-s3/result.json` |
| S4 设置/BYOK | `docs/evidence/v3-s4/result.json` |
| S5 候选启动 | `docs/evidence/v3-s5/candidate.json` |

## 审阅者最小动作

1. 核对 exe SHA 与 `checksums.txt`、git SHA 一致。
2. 干净 Windows 解压 onedir，设置 `DT_V3_DATA_DIR` 到空目录，确认未写日用 `config.json`。
3. 复现 S2：生产页真实请求，图片先于文字进入指定目标，不是 Cursor 冒充。
4. 抽查拒绝截图后文字仍可同步；手机不能自授插入。
5. 结论只能是 `PASS` / `REQUEST_CHANGES` / `BLOCKED_ENV`。缺少真机时不得把相关条目标成产品 PASS。

## 当前结论

`WAITING` — 实现者未签署。未得到独立复核前，不得把状态写成 RELEASE_READY 或 PUBLISHED。
