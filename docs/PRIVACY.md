# 隐私与数据 / Privacy and data

## 中文

- 手机网页通过配对后的本地网络连接电脑。草稿、图片和恢复记录保存在手机浏览器及电脑工作区。清理浏览器站点数据会影响手机本地恢复。
- 截取电脑内容需要授权及明确操作；不要把配对信息、截图或桥接端口开放给不可信的人。
- 不启用模型功能时，原文输入、编辑、图像和插入不需要模型API。Jev默认关闭；开启时仅把当前文字发给所选服务商，不包含图片、历史对话或目标Agent结果。
- 纠错/改写使用独立配置的模型接口。其请求受所选服务商的隐私和保留政策约束；不是“所有内容永不离开设备”。
- Windows模型密钥通过系统凭据存储管理；不要把Key、配对令牌、私人草稿放进GitHub Issue。检查更新会访问GitHub。
- 断线、关闭浮窗和卸载不等于删除所有本地记录。数据目录和备份位置见安装指南；需要清理时先导出要保留的内容。

## English

The paired phone page communicates with the desktop bridge over your network. Drafts, images and recovery records are kept in browser storage and the desktop workspace. Clearing site data can remove phone recovery data. Desktop capture requires authorization and an explicit action.

Core input, editing, images and insertion do not require a model API. Jev is off by default; enabling it sends current text to the selected provider, without images, conversation history or target-agent results. Rewriting uses its separately configured endpoint. Provider privacy/retention terms apply, so “all content always stays on-device” would be inaccurate.

Windows API keys are managed through system credential storage. Update checks contact GitHub. Do not share keys, pairing tokens or private drafts in issues, and do not expose the bridge to the public internet. Disconnecting, hiding the overlay or uninstalling does not erase every local record; consult the installation guide for workspace and backup locations.
