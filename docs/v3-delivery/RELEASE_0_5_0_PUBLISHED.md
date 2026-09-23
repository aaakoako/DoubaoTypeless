# 0.5.0 正式发行记录

已按用户明确授权合入默认分支 master，并于 2026-09-23T17:38:19Z 公开 [v0.5.0](https://github.com/aaakoako/DoubaoTypeless/releases/tag/v0.5.0)，设为最新稳定版。用户最初的「不merge、不tag、不Release」临时边界已由后续明确发行要求覆盖；未覆盖日用配置或强制结束用户进程。

- 正式源码：`aac1e51ab13e3107d0264ebb940b50f088f068c7`；与已审查、验证的候选 `29a32ffeef0e04ca1cfec1ce0d0198d681a2b003` 文件树一致。
- 正式 CI：[35894995695](https://github.com/aaakoako/DoubaoTypeless/actions/runs/35894995695)；发行验证：[35895043850](https://github.com/aaakoako/DoubaoTypeless/actions/runs/35895043850)。
- Windows 632 项、Linux 623 项（9 项平台跳过）、18 项证据检查通过。正式包7份原生报告、14个图文场景、官方0.4.2下载/退出/整体替换/重启及失败恢复通过。
- 下载后核对267个文件、SHA-256及build-info；本机离屏再次验证启动和正常退出。完整升级入口SHA-256：`bc2e171e73180e419f02c0ffeb0b4fe88dabc59d31807a1c87e233eb29b09314`。
- 公开 latest 接口返回0.5.0、draft=false、prerelease=false。更早内部0.5.1/0.5.2候选需手动运行完整安装包，其旧版本比较逻辑不能远程改变。

## 模型与交互

真实OpenRouter调用详见 [JEV_INPUT_CHECK.md](JEV_INPUT_CHECK.md)。Key通过用户填写的独立密码窗保存至用户环境变量与系统凭据，源码与发行包不包含Key。Jev默认关闭，普通复制/插入不依赖模型。

新增语气、愤怒火焰、输入/点击/面板/图片动效，以及独立模型服务商和地址补全。动效由应用内开关控制，不跟随系统reduce-motion。源码审查发现的Key绑定、接口完整路径、愤怒门槛回落问题均修复。云端暴露的首次HUD追尾停在末尾4px之前问题，已通过直接复现和不等待计时器的回归修复。

## 验证边界与后续

用户确认此前候选在Codex桌面端图片后正文连续插入成功；不是自动化实测当前Codex的声明。Cursor、实体手机输入法和多屏仍按各实际环境验证。

原生浏览器用例仍产生0x8001010d诊断记录，但同一PID完成全部14场景并正常退出；保留调查记录，不把该日志直接认定为终止崩溃，也不宣称所有环境无故障。构建载荷中的release_ready=false是构建工具不自行宣称实机验收的标记；公开发行决定另由本记录、用户授权与实际发布状态表示。

本机交付：`G:/AgentStorage/Deliveries/DoubaoTypeless-0.5.0`。入口「体验 0.5.0.lnk」沿用隔离的OpenRouter配置；安装包仍使用正常固定工作区。完整校验和原生报告位于交付目录evidence。
