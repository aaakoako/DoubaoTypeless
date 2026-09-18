# 检查器：只筛查证据一致性，不执行产品验收

`check_release_evidence.py` 是可直接运行的Python 3.11+标准库工具。本轮已执行18项工具自测，见 `../evidence/checker-selftest.txt`。这些不是18项V3产品通过记录。

它只读本地文件，不联网、不运行传入命令、不写PASS、不操作剪贴板、不更新GitHub，也绝不签发Release授权。

## 最先可执行的检查

从本补丁目录运行：

```bash
python -m unittest discover -s tests -v
python tools/check_release_evidence.py templates/candidate.example.json --evidence-root . --expected-sha 9dd3a369f1b566d0fdc548cee3af934523e9b8db
```

第一条测试本检查器；第二条对所有96项NOT_RUN的示例应返回 `REJECTED`、退出码1。示例没有真实制品，不是对当前仓库重新审计的报告。

## 真正接入CI之前要完成的工作

1. 开发Agent建立生产测试，输出JUnit、浏览器trace、Windows/Android脱敏记录、包和哈希。
2. 为每条AC3定义映射真实测试及完整观察，生成candidate.json；不能按固定列表填PASS。
3. `--expected-sha` 来自可信构建任务选定的源码SHA，不从不可信报告里取值来与自己比较。最终包文件来自固定构建产物。
4. 检查器读取的catalog应来自已审查版本；不能同时改脚本/冻结哈希/目录定义逃避门槛。真实权限保护需在仓库建立，本包没有替你配置。
5. 运行结构筛查后，独立检查证据覆盖范围、来源、断言和实际用户体验；不能让结构通过直接触发Release。

## candidate.json说明

顶层包含 `schema_version: 1`、`tested_commit`、`artifact`、`cases`。
`artifact` 包含相对路径path、实际文件sha256、built_from完整SHA。
96项case ID必须齐全且唯一；期望进入候选的各项status须为PASS，每项附receipts。

每个receipt必须含：

- kind：automated / windows_native / android_native / ci / build / review / static_review；最低类型来自冻结目录，不满足时拒绝。
- tested_commit、executed_at（带时区ISO时间）、executor、observed、expected、environment（含version）。
- files：每个是 `{ "path": "相对证据路径", "sha256": "真实哈希" }`。
- automated / ci / build还需command及真实exit_code=0；automated/ci需junit指向files中被哈希的XML、精确classname/name；无testcase、failure、error、skipped都不能通过。
- Windows原生环境需 `os: Windows`、`real_target: true`；Android原生需 `os: Android`、`physical_device: true`。这些字段是记录要求，不是设备真实性的自动证明。
- windows_native / android_native / build还需artifact_sha256与候选归档文件一致，证明申报测试的对象；真正来源仍由独立复核确认。

最终证据应针对冻结源码/固定包重新取得；平时开发测试的旧证据作为过程材料保留，不偷换成最终候选证据。记录保存在构建artifact或单独证据目录，不把证据自身的提交SHA当被测源码SHA。

命令模板：

```text
python tools/check_release_evidence.py candidate.json --evidence-root <证据及候选包目录> --expected-sha <候选完整源码SHA>
```

目录外路径、URL当本地文件、路径穿越、空文件、哈希变化都会被拒绝。Python/TypeScript等源文件不能当作运行层证据；静态审查允许引用源码，但不得替代原生结果。

## 输出与边界

- 退出码1 / REJECTED：必需证据缺失或不一致，不能进入可发布判断。
- 退出码2 / INVALID_INPUT：报告无效、目录被修改等，不能判通过。
- 退出码0 / EVIDENCE_STRUCTURE_OK_REQUIRES_INDEPENDENT_REVIEW：仅结构一致；不是“V3测试通过”。

任何输出都含 `product_verified_by_this_tool: false`（输入无效输出除外）和 `release_authorized: false`。

脚本不能验证：录像是不是实际拍摄、声明设备是否真实、测试断言是否覆盖完整预期、是否操作了别处的数据、最终手感是否好、实现者是否伪造了语法有效日志。这里需要可信CI来源、独立复核与真实用户试用。单个检查脚本不能解决全部这些问题。
