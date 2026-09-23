# 给Grok的返修指令（独立审查后）

你提交的`v3/00-baseline@9dd3a369f1b566d0fdc548cee3af934523e9b8db`独立复核结果是REQUEST_CHANGES，不是仅剩真机。先读取本包INDEPENDENT_REVIEW.md、环境和反例输出，再读取当前真实仓库，确认HEAD/工作区差异。不要reset/覆盖用户改动。不要改master，不merge、不推标签、不发布Release、不覆盖日用目录。

先完成R0＋R1；每批提交后停止并给出证据，不一次性再宣称全24卡完成。

R0：当前GitHub run35323737872因缺Pillow有6个collection errors。补齐明确的测试依赖，实际跑CI。逐条重审acceptance.json中PASS；源码存在、脚本返回0、文件存在都不算产品验收。不删除旧证据，但给旧样板注明适用提交和范围。不得再用v3_fill_acceptance.py静态MAP批量生成PASS。

R1：移除GET /v3/pair公开返回挑战的授权漏洞；远端不能自授截图/插入权限。每个WS/HTTP变更先鉴权并绑定批准设备，不得在insert.intent鉴权前修改草稿；拒绝不产生副作用。先获实例锁再初始化写入服务，获锁失败必须停止，不杀旧进程。使用独立临时数据/loopback测试。

后续必须依顺序处理：
1. 真实前端asset_refs→后端已校验资产解析；截图源图与导出成品分离，裁剪/遮挡后不得插入原图；受鉴权图片通过带头fetch→blob加载；修复默认1MiB chunk触发413；兼容选定的HTTP局域网安全上下文或真实部署HTTPS。
2. Qt更新通过主线程queued signal；从真实WS触发原生可见性验收，不断言visible变量就结束。
3. 确定目标控件/窗口/文档身份，不比较classify_focus类别就当同目标；等待修饰键后再核验，真实远端unknown目标拒绝；已执行过步骤不能返回NO_STEPS。
4. Alt+I冻结当前稿B；Alt+Shift+I召回上次A并在新目标重试；UNKNOWN必须有真实选择UI，不能ask→full默认；部分补贴传正确的已确认资产集合，不覆盖当前稿。
5. Undo先记操作前状态；图片scene可再次编辑；补双指平移和固定像素导出；草稿落盘后再durable ACK，重连/重启只恢复数据不重放动作。
6. BYOK/设置/引导/历史恢复必须有真实可达入口。当前ByokService无默认transport、手机版设置只有说明，不能宣称产品已完成。

本包14项测试是固定旧SHA的独立反例，10个源文件已核对Git blob。把反例移植到真实工程测试中，以修改后的模块运行；不要修改审计包归档源码、改期望或删用例来制造通过。保留实际E2E生产请求，不允许像旧product_pass工具一样偷偷添加真实页面没发的assets字段。禁止用模拟V3ComposerTarget当作真实Cursor通过。

交付必须区分：SOURCE_FACT、COMPONENT_RUNTIME、NATIVE_RUNTIME、NOT_RUN/BLOCKED。每项写固定提交、测试输入、实际输出、命令退出码、文件路径、证据hash、未验边界。真实豆包/真实Cursor环境没有就继续BLOCKED_NATIVE，但已知代码缺陷要写FAIL，不拿缺设备掩盖。

不可恢复/未经观察的图像结果不能冒称CONFIRMED；Enter不发送；不得Ctrl+A/Delete清用户已有内容。日用配置、词库、历史、注册表和凭据只读验证，不上传敏感正文。
