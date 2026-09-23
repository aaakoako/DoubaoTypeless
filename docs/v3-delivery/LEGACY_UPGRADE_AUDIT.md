# 0.4.2 升级断点核查（2026-09-23）

结论：当前 b69f7bc 候选不能宣称支持 0.4.2 无缝升级。用户补充的历史症状为“下载完成后退出，但没有重新打开”。此前安装器验证只覆盖 V3 布局与数据，没有覆盖真实 0.4.2 更新链路。

## 已确认的问题

- v0.4.2 的 updater.py 与核查前工作树一致。更新器只选择一个 EXE，删除旧文件、将下载文件改成旧名称后启动。新版公开附件若沿用当前候选的 Setup.exe / portable.zip 布局，旧选择器会选择 Setup.exe；旧应用入口因此变为安装器。未实际对用户旧程序执行替换。
- 重启子进程继承 PyInstaller 运行环境，没有设置 PYINSTALLER_RESET_ENVIRONMENT。隔离 onefile 实验在旧进程退出并移除临时运行目录后，继承环境的重启报 Failed to load Python DLL、退出码 4294967295；设置该变量后退出码 0 且生成启动标记。它是与症状吻合的可复现机制，不能替代缺失的用户历史日志。
- 备用 PowerShell 命令用了 Start-Process -LiteralPath。Windows PowerShell 的参数表确认不存在此参数，应使用 -FilePath。
- 旧 config.json 与 data 存在旧 EXE 旁；V3 使用独立 workspace-v3。inspect_legacy_config 只有检查函数与测试调用，没有生产导入入口，不能声称已迁移配置、词库或历史。
- 旧自启动注册值名为 DoubaoTypeless，新版使用 DoubaoTypelessV3；现有安装器仅接续新版键，不处理旧版入口。
- 旧更新器先删除旧 EXE，缺少完整回滚和启动就绪验证。cmd start 返回不等于新应用成功初始化。

## 本轮修改及验证范围

在遗留源码中补充重启环境重置（普通启动和计划任务共用的批处理均覆盖），修正备用参数，只允许明确的 DoubaoTypeless.exe 单文件附件进入旧替换流程；遇安装器给出保留旧程序和数据、查看迁移说明的提示。tests/test_core_logic.py 的 13 项回归通过。

这些修复尚未进入已发布的 v0.4.2，也不在固定 b69f7bc 候选里。V3 的更新入口本身仅打开下载页，不调用这个遗留更新器。不能通过修改仓库源码，反向改变用户手里的旧程序。

隔离实验材料：G:\AgentStorage\Caches\typeless-upgrade-probe-20260923，包含 probe.py、worker.py、build.log、inherited.json、reset.json 与重启标记。实验不启动用户应用、不修改日用数据、不操作用户键鼠。额外兼容性 JSON 报告生成命令被自动审批拒绝，仅返回 blocked by policy，未执行。

依据：[PyInstaller 重启文档](https://pyinstaller.org/en/latest/common-issues-and-pitfalls.html#using-sys-executable-to-spawn-subprocesses-that-outlive-the-application-process-implementing-application-restart)、[Start-Process 参数](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/start-process)。

## 发布前仍需打通

1. 明确旧安装用户可完成的引导升级路径：旧客户端已发布逻辑不可修改，新包必须兼容它，或提供明确的人工过渡步骤，不能让旧检查更新误替换成安装器。
2. 只读导入旧配置、API Key、词库和历史，处理自定义路径；迁移前备份，失败保留旧数据，已有 V3 数据不被覆盖。旧后台学习和权限不得被悄悄重新开启。
3. 安装成功后验证新版启动就绪，再处理快捷方式、自启动和旧版回退；失败时旧程序仍可打开。
4. 用实际发布的 0.4.2 单文件版、便携版经过用户入口验证下载、退出、替换/安装、重启及内容保留；断网、文件占用、失败恢复均应有可用结果。

在这些项完成前，release_ready 继续为 false，不合并、不打标签、不公开发布。
