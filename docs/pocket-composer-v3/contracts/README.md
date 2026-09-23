# 合同范围与校验

这三个JSON Schema定义本次冻结图文、投递意图、步骤记录的核心形状；不是完整服务器实现，不包含全部WS消息/HTTP鉴权。全部传输消息仍须按spec/04实现封装、权限、速率、期限和所属设备校验。示例nonce只是测试字符串。

## 固定哈希算法

Bundle只允许ASCII字段名、整数版本/尺寸、布尔、字符串、数组和对象。计算时移除manifest_hash字段；递归按字段名的ASCII顺序排序；无空格、UTF-8、中文不转\\u，不改变换行/缩进、不做Unicode规范化；禁止NaN、浮点和孤立代理项。JSON字符串使用标准转义：控制字符、双引号、反斜杠；不额外转义斜杠、U+2028/U+2029。数组顺序保留。Python参考ensure_ascii=False/separators/ sort_keys；JS须递归排序后JSON.stringify，不得使用普通对象遍历结果代替规范化。对实际字节取SHA256小写hex。fixtures/manifest.canonical.json是跨语言金标准。

## Schema以外必须检查

text限制按UTF-8字节≤65536，不只是字符数；图片合计≤24MiB、asset_id不可重复；正文全空且0图禁止；协议3不能接收字符串3或布尔true作为revision；所有图片文件必须实际存在并验证哈希/魔数/尺寸/大小；禁止原图路径和源图层加入网络Bundle。

Intent必须在已批准连接上，session_nonce从服务器短期发放(10秒)，按intent_id持久去重(24小时)，绑定session/bundle/hash；过期或同ID不同内容拒绝。**不能仅凭本Schema“valid”允许系统输入。**

Attempt的CONFIRMED要求全部预期步骤有接收方/用户证据，不能用os_input_count冒充observed；任何未确认图片都阻止自动贴后续文字。重试范围与目标身份还要按spec/03验证。

## 检查

安装jsonschema，运行 `python tools/check_contracts.py`。它只检查示例合同和负例，不证明生产鉴权或原生插入已实现。
