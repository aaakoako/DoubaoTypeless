# 图文进度与 Composer 定位工作记录

基础源SHA：30421e3cb306402ef2a67ca54b6e8824f9f2630d。此文件不是发布批准。

## 已做
- 执行真实DeliveryService，图片观察返回unknown时，序列只有image→paste，无text；保留此安全边界而不是直接删掉等待。
- 新增delivery_progress，并接入应用完成/错误事件、HUD与恢复框，明确区分文字未尝试和已发出未确认。
- composer_locator只扫描指定应用窗口，已有MTA辅助进程承载；数值身份传回。强标识+可编辑属性，拒绝搜索/代码/终端/密码/只读/屏外控件；遍历不完整不宣称唯一。
- 原生托盘接入“定位当前窗口输入框（不插入）”。只有唯一候选或精确记住的身份才聚焦；扫描期间目标变动则停止。尚无已验证的各种Agent通用适配。
- Qt与手机源样式换为雾蓝灰+蓝紫；没有生成新图标、前端产物或EXE。

## 验证
`PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_v3_composer_progress.py tests/test_v3_assistant_delivery.py tests/test_v3_input_identity.py tests/test_v3_stability_contract.py --tb=short`

78 passed；其中34项新增。新查找的原生系统接口为显式替身；脚本并未实际扫描/移动用户Windows窗口。Python语法检查和git diff --check通过。没有全仓通过结论。

本环境安装PySide6失败（DNS不可达），未跑本次Qt原生界面测试；HTML配色参考已在本机Chromium渲染，不作为应用截图。

## 未解决/不能误称通过
- 用户那次图片后文字未入框尚无操作日志，只验证了能造成同类表现的真实代码路径。
- 支持目标上的附件完成识别、上传后目标重新确认、自动继续文字还须专项实现与Windows混合投递验收。
- 多候选实际列表、手动指定后长期记忆/版本兼容矩阵尚未完成。
- 当前GitHub工具集只有读操作；没有推送、云端构建或新包。

## 整合
对当前真实HEAD比较后应用补丁。仅在隔离分支，不覆盖新修复、不修改日用数据、不merge/tag/Release。继续原MASTER_PLAN，不停在本补丁和本地测试数字上。
