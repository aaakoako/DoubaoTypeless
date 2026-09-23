# 本轮交付状态

日期2026-09-18。本轮交付为设计v3，不是应用版本v3。

|项目|实际状态|证据/边界|
|---|---|---|
|远端基线|已再次查询|master=e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5；本轮未写仓库|
|旧附件读取|已执行|读取已有设计手册，取消与新需求冲突的常驻/大窗/四标签决定|
|产品与开发规格|已生成|README、11份spec、24任务卡、96项产品用例、3份核心JSON Schema|
|浏览器原型行为|34/34通过|evidence/prototype-report.json；Linux Chromium离线set_content，不是真机|
|参考合同检查|25/25通过|evidence/contracts-report.json；验证参考数据和负例，不是服务器|
|颜色参数检查|6/6达到选定目标|contrast-report.json；非完整无障碍认证|
|真实产品验收|全部96项NOT_RUN|fixtures/acceptance.json；不可把原型结果写成产品PASS|
|Windows原生运行/出包|未执行|没有新EXE，没有真实窗口/剪贴板/热键实测|
|手机输入法/多指/软键盘|未执行真机验收|桌面浏览器响应式检查不替代真实Android输入法|
|Cursor完整先图后文|未验证|G0首个硬门槛；不可观察附件时降级但不能算完整一键完成|
|BYOK真实调用、配对加密|未执行|本轮没有用户Key，没有真实鉴权服务器|

## 已知原型差异

完整说明见prototype/README.md。原型是有部分真实画布操作的设计工具，截图/传输/投递均模拟；裁剪手柄、图序、对象缩放、键盘抽屉、真实存储/图片预算等按规格继续开发。原型与产品不共享“已通过”口径。

## 实际运行命令

```
node --check /mnt/data/prototype_check.js
python tools/check_contracts.py
python tools/check_prototype.py
python tools/render_previews.py
```

JavaScript语法检查针对从原型HTML提取的脚本，不是生产web工程编译；没有执行npm build/PyInstaller，因为本轮没有把设计实现到源码。检查脚本可在装有依赖和Chromium的环境重跑；CHROMIUM_PATH指定浏览器路径。脚本与报告包含在本包，依赖不打包。

本轮通过container检查并生成原型屏幕图，不使用OCR。没有分发系统字体或第三方私密图像。
