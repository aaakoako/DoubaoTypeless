# 从这里继续整个 V3

这是产品开发任务，不是又一次只改文档。审查基线：`4eb8c4454a879e6b7ce11cf47e1bb0bfdba93b9a`。

将本目录放进仓库 `docs/v3-product/`。唯一规范正文是 `MASTER_PLAN.md`；先读第0–2节，再通读第3–6节，之后按当前阶段回查。`UI_BOARD.html` 是视觉规格辅助，不是产品实现。`COVERAGE.json` 是原96条与体验补充的索引，不是通过报告。

首次接手先记录完整HEAD、当前工作区和已存在的修复，与本基线比较，不reset、不覆盖。更新现有 `AGENTS.md` 与 `.cursor/rules/v3-delivery.mdc` 的V3入口指向这里；旧文档只加历史导航说明，不删除旧证据。不要新写一套平行计划或要求用户重发旧包。

本次授权是隔离分支内完整开发、自测、修复和生成候选；不允许自动合并master、打标签、发布Release或覆盖日用数据。总目标不是一个切片：完成所有原定能力、保留旧好体验、交付完整可发布候选。

S0→S5是内部顺序；切片完成后继续下个可执行项，不等用户逐卡指挥。按需要重开旧任务，而不是从 `CHECKPOINT.open_defects=[]` 推断没有缺陷。本报告列了18处当前问题和41项能力处理，逐一落实。以真实操作和截图验证，不是凑更多PASS数字。

会话结束前更新现有CHECKPOINT并记录下一条具体开发动作；下一轮一句“继续V3”即可续跑。缺设备只阻塞对应设备验证；界面、协议、CI、可安装开发依赖和适配器实现不能一并扔给设备持有者。

隔离预览（不要用 `python -m doubao_typeless`，该入口在当前包布局下不可运行；`AGENTS.md` 受 AC3-004 冻结，正确命令写在这里）：

```bash
$env:DT_V3_DATA_DIR="$env:LOCALAPPDATA\DoubaoTypeless\preview-v3"
$env:PYTHONPATH="src"
python tools/run_v3.py
```

## 必须记住

主路径：手机说一段 → 看清/电脑可改字 → **插入并复制** → 收起浮窗 → 手机空白新稿 → 上次仍可恢复。
新增路径：截图/相册/白板 → 裁剪标注 → 完成处理图 → 真实目标图片先文字后，不按Enter。

“保存上一段”“是否确认外部接收”“当前开始下一段”“窗口隐藏”四个决定独立。不能为了安全让手机永远留着旧稿，也不能为了清空把UNKNOWN伪造为CONFIRMED。

## 文件说明

- MASTER_PLAN.md：唯一完整产品/审查/设计/开发/验收计划。
- GROK_PROMPT.md：可以整段发给Grok的任务指令；不是另一个规格。
- UI_BOARD.html：更新后的平面界面规格示意，可离线切换页面/查看长短浮窗，非生产系统。
- COVERAGE.json：原96条定义快照、S阶段、覆盖说明与24条体验补充；默认无产品通过结果。
- evidence/REVIEW_OBSERVATIONS.json：本次最新CI观察、提交关系、换行哈希及审查边界。
- evidence/REVIEW_INDEX.json：41项能力和18项问题的机器可读索引。
- evidence/HANDOFF_CHECK.json：此交付文件完整性检查，绝不是V3产品测试。

无需再让用户发送旧版多个互相覆盖的包。原图文设计的安全与手机工具要求已整合在MASTER_PLAN，旧资源只作必要参考。
