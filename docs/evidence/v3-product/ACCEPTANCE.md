# 产品路径证据（不是设计原型）

命令：`python tools/v3_product_pass.py`  
退出码：0  
提交后 SHA 以 git 为准。

## 这次实跑通过的门槛

| 门槛 | 结果 |
|---|---|
| 空闲无 DT-V3-HUD | PASS |
| 产品 Composer（`/` 来自 `composer.html`，不是 prototype） | PASS |
| 先图后文：两张不同图进入真实窗口 | PASS |
| 文字出现在图后 | PASS |
| Enter=0 | PASS |
| auto_send=false | PASS |
| 目标观察 CONFIRMED（product_target） | PASS |
| 仓库 config.json 未写 | PASS |

截图：`01-idle-target.png`、`02-idle-after-app.png`、`03-after-insert.png`。

## 仍然不是 Cursor Composer 一键验收

`AC3-006` 要求真实 Cursor Composer 附件。本次目标窗是产品验收窗 `V3ComposerTarget · chatinput`，适配器记为 `product_target`，**不能**写成 Cursor Composer PASS。

## 仍然没有真机豆包输入法

`AC3-002` / `AC3-037` 的 Android IME 仍为 BLOCKED_NATIVE。产品页已由真实 aiohttp 提供，浏览器/协议驱动不等于手机输入法。
