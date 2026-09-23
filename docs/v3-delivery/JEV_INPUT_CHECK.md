# 0.5.2 Jev 输入检查

在电脑「常用设置」选择 TypeSafe 或 Vercel AI Gateway，填写对应 Key，检测连接，开启输入检查并保存。申请入口：https://console.typesafe.ai/ 或 https://vercel.com/ai-gateway 。连接检测只发送固定示例文字；启用后发送当前稿文字，不发送图片和历史。两家 Key 分开保存在系统凭据库；系统凭据不可用时沿用现有会话保存方式。

浮窗显示疑似转写错误、歧义、缺项或上下文依赖，展开可看对应原句。表达语气可单独关闭。可选语音说明只提示文字可能有误，不要求目标模型向用户确认。误判时可在浮窗取消本段附注；同段继续修改不会自动重新开启。

按用户后续要求，界面使用 SVG 图标加短文本：浮窗仅保留问题数量、语气和附注状态，原句移入展开详情。语气图标保留中文标签；完整附注文案可悬停查看。

检查在后台进行，复制和插入随时可用。等待中或检查失败时使用原文，失败后可在展开面板点击「重新检查」。只对提交时已完成的当前文字判断附注，后到结果不改变本次内容。插入附注不污染原稿，恢复仍取原稿。

实际 UI 截图由正式 Qt 控件离屏渲染；判断响应为明确替身，不是 Jev 推理结果。已验证请求/响应契约、旧结果隔离、暂停/关闭/重试、手机主稿及电脑编辑回执、复制退路、恢复原文与凭据分离。尚未进行真实 Jev 中文误报率、延迟、费用测量；Codex/Cursor/实体手机验收仍待实际体验，不能由新功能回归替代。

官方资料：

- https://docs.typesafe.ai/api ：结构化 Choice 接口。
- https://docs.typesafe.ai/models ：模型和语言能力边界。
- https://docs.typesafe.ai/model-jaggedness/jev-1.13 ：窄范围判断能力。

未发现官方可下载权重/本地运行发行包，本实现调用官方托管 API。原有改写模型设置保持独立。

用户后续选择 Vercel。使用官方 TypeSafe 兼容接口 `https://ai-gateway.vercel.sh/typesafe/v1/systemone`，模型 `typesafe-ai/jev`，保留相同结构化判断；不把 Jev 当作 Chat Completions 模型。接口依据：https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe 。

2026-09-23 实际 Key 验证：模型列表与余额接口成功，余额和累计用量均为 0；推理返回 403 `customer_verification_required`，要求在 Vercel 后台添加有效信用卡解锁免费额度。产品用固定短标签「需激活额度」呈现，完整解释置于详情/悬停。未购买、未更改付款设置、未获得任何真实模型判断。免费层仅部分模型可用，具体账户激活后的 Jev 权限仍以实测为准：https://vercel.com/docs/ai-gateway/pricing 。

本机为用户建立隔离体验配置 `G:\AgentStorage\Workspaces\DoubaoTypeless-Jev-Preview`；Key 仅在 Windows 凭据库，不在源码、文档、诊断或候选包。候选可提供指向该配置的体验入口，用户当前运行程序和旧数据保持原样。

## 候选回归中发现的启动竞态

524a802 的发行前验证通过，但独立 CI Windows 的旧有延迟监听测试出现失败。本地连续运行在第 12 轮复现：控制日志中客户端 connected 早于服务端 listening 日志，之后没有 received，客户端在期限内未获得回执。

QLocalServer 原生监听启动与 newConnection 处理器注册之间已经可能收到连接。修复在注册处理器后立即排空已有待处理连接；保留逐连接完成标记和回复写出后再执行，不重发命令、不扩大期限。新增真实跨进程 show/quit 提前连接回归；移除修复的运行反证两项均失败，带修复五项均通过。独立只读复核未发现重复分发或资源归属问题。

新界面测试另有一次 Linux 失败，原因是设置保存路径调用 Windows 全局热键。界面测试现在明确替换 OS 热键注册，继续执行真实设置保存及 Qt 控件；原生快捷键行为由既有 Windows 候选验证覆盖，不冒充 Linux 原生热键已验证。
