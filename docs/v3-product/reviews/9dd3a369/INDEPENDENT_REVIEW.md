# DoubaoTypeless V3 独立复核：REQUEST_CHANGES

复核日期：2026-09-18  
固定提交：`9dd3a369f1b566d0fdc548cee3af934523e9b8db`  
分支：`v3/00-baseline`  
对照主分支：`6bf98e7b26598db8e53ebe1abf3991fa44f3241c`  
共同基线：`e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5`

## 结论

**不能认定“V3已做完，仅剩真机”。建议保持隔离分支，REQUEST_CHANGES，不合并、不发布、不替换日用版本。**

确有新的产品代码、数据模型、测试工具和原生样板记录；不能说全部是空壳，也没有证据指控实现者故意伪造全部运行日志。问题是：部分产品验收被源码存在或弱断言直接升级为PASS，真实前端和后端没有接通，且存在明确的授权、图像投递和恢复缺陷。真实豆包输入法、真实Cursor附件观察仍应保持未验状态，但它们不能解释本报告已经确认的代码缺陷。

## 1. 我实际做了什么，以及没有做什么

通过已连接GitHub读取固定提交、分支/对比、关键实现、验收表、生成验收的脚本及GitHub Actions原始日志；核对原V3规格。未修改远端文件、分支、PR、标签或Release，也未接触用户Windows日用目录。

网络克隆在当前执行环境不可用，因此没有把“已读若干文件”写成“完整克隆并跑过所有测试”。我把10个已完整读取的Python源文件按原内容放入本地，并逐个验证Git blob SHA-1与GitHub返回值一致。直接导入纯逻辑模块；对V3Bridge/V3App执行未改动的类AST，注入明确的内存依赖替身，以避开缺失的完整工程和Windows依赖。HTTP/WS反例只连本地127.0.0.1，截图、剪贴板和系统发键均未执行。

本轮独立检查结果：

```text
python -m pytest -q tests_expected_behaviour.py --tb=short --junitxml=regression-results.xml
12 failed, 2 passed
exit code: 1
```

这14项是**专门针对疑似缺陷的期望行为测试**，不是原工程76项测试，也不是随机抽样的产品合格率。12项失败表示对应预期未满足；2项控制检查分别证明源文件哈希一致、未知附件结果不会继续贴文字。

实际Windows GUI/热键/剪贴板、真实手机豆包输入法、真实Cursor均未由本轮运行。浏览器安全上下文探针尝试被环境策略`ERR_BLOCKED_BY_ADMINISTRATOR`阻止，因此相关问题依据源码与官方文档，不伪称浏览器实测成功。

### GitHub CI：当前提交确实失败

[运行35323737872](https://github.com/aaakoako/DoubaoTypeless/actions/runs/35323737872) 的`head_sha`就是本次提交，结论`failure`。实际读取job `105531882445`日志：缺少`PIL`，6个测试模块在collection阶段失败，pytest退出码2；后续“Confirm no release side effects”步骤被跳过。

[`.github/workflows/preview-v3.yml`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/.github/workflows/preview-v3.yml) 只安装pytest/httpx/aiohttp，没有安装Pillow。这不证明“本地76 passed”一定虚假，但确实证明当前干净CI没有通过，不能拿本地摘要覆盖云端失败。

## 2. 用户特别要求的三项检查

| 项目 | 复核判断 | 边界 |
|---|---|---|
| 假PASS | 已确认有无充分证据的PASS，部分与代码行为直接矛盾 | 不等于断言76个本地单测结果全是伪造 |
| Enter | 已读V3生产发键路径只见Ctrl+V，没有发现显式Enter注入 | `enter_count`初始化为0不能独立证明所有真实路径；目标提交行为仍要原生记录 |
| 日用数据 | 默认路径独立，已读迁移函数只读；没有发现默认路径主动写旧config/history的代码 | 现有证据没有覆盖实际日用安装目录的完整前后快照，不能保证整台电脑未改任何文件 |

### 日用数据的具体边界

[`src/doubao_typeless/runtime.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/runtime.py) 默认使用`%LOCALAPPDATA%/DoubaoTypeless/preview-v3`，这是值得保留的隔离方式；[`src/doubao_typeless/storage/migration.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/storage/migration.py)读取旧配置，不保存回旧文件。

但是 [`docs/evidence/baseline/AC3-004/daily-use-snapshot.json`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/docs/evidence/baseline/AC3-004/daily-use-snapshot.json)主要记录仓库文件、标准AppData路径不存在；[`tools/v3_product_pass.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/tools/v3_product_pass.py)的`repo_config_untouched`只检查仓库根目录`config.json`是否不存在。该证据不等于用户另一个安装目录、词库、历史、注册表、凭据库的前后对比。

`DT_V3_DATA_DIR`覆盖路径没有防止指向日用目录；实例锁失败后程序继续启动，见F14。应继续只用独立预览目录，并为实际日用目录补只读哈希快照。不要以复核为名复制敏感配置正文进仓库。

### 远端副作用

读取到master仍是README图文提交`6bf98e7...`，未包含V3提交；V3分支相对master前进5个提交、缺少master的1个README提交，共同基线仍为`e6b5b085...`。这不是已经覆盖README。当前标签列表未见V3标签，公开Release仍以v0.4.2为最新。本次新增preview工作流本身无发标签/Release操作。只能描述当前可见状态，不能据此证明历史上绝不存在随后已删除的对象。

## 3. 阻断问题与最小修复

优先级口径：P0为授权、隐私或错误目标/重复投递风险，阻止日用接入；P1为核心功能、可验收性或稳定性缺陷；P2为附加体验/维护问题。优先级是本次工程判断。

### F01 · P0 · 配对允许请求方自行取得权限

**证据：** [`src/doubao_typeless/services/bridge_v3.py` · 110–126](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/bridge_v3.py#L110-L126)、[`src/doubao_typeless/storage/credentials.py` · 48–84](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/storage/credentials.py#L48-L84)。

GET `/v3/pair`在无鉴权情况下返回配对挑战；POST `/v3/pair`直接接收远端提供的`allow_insert`和`allow_capture`。本机没有批准环节。授权服务虽然有随机令牌和过期时间，但取得令牌的前提被公开接口绕过。

**本轮复现R01：** 仅在本地测试服务器发GET和POST，不经过桌面批准，取得两个权限均为true的session。未调用任何真实截图或键盘。

**影响：** 能访问桥接端口的人可自行取得会话权限；风险边界是可访问该监听端口的网络，不等于默认公网可访问。

**最小修复：** 配对挑战只经电脑本地UI/授权渠道发放；权限由电脑批准而不是请求体决定；配对尝试限流；会话与设备绑定；撤销关闭连接。首次未批准、拒绝、过期、撤销均需端到端测试。不得通过删掉配对功能或声称“局域网所以安全”解决。对应AC3-017–020、080、092。

### F02 · P0 · 未配对连接可以修改/冻结草稿

**证据：** [`src/doubao_typeless/services/bridge_v3.py` · 232–329](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/bridge_v3.py#L232-L329)。

`session.hello`可不带session；`draft.update`、`editor.activity`、`bundle.commit`不检查会话；`insert.intent`在验证权限前就可能改草稿。

**复现R02：** 无session/token的WebSocket发送draft.update，被接受并返回`draft.ack`，原草稿变为未授权文字。R01不成立之前，此问题也单独存在。

**最小修复：** WS握手后绑定已批准session，所有数据变更/读取先鉴权；输入模型验证在变更前完成；拒绝时草稿、版本、历史均不变化；按设备/会话校验图像归属、Origin和请求限流。不允许“先改数据，随后鉴权失败”。

### F03 · P0 · 图片引用未接入冻结内容，处理后的图可能被原截图替代

**证据：** [`web/src/app.ts`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/web/src/app.ts)中`sendDraft/finishEditor/sendBtn`，[`src/doubao_typeless/services/bridge_v3.py` · 249–316](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/bridge_v3.py#L249-L316)、[`src/doubao_typeless/core/bundle.py` · 58–113](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/core/bundle.py#L58-L113)、[`src/doubao_typeless/app.py` · 101–115](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/app.py#L101-L115)。

手机发`asset_refs`，后端仅用refs计算哈希；真正写入/冻结的是`draft.assets`，仅实际携带`assets`字段才更新。上传完成接口也不把refs解析为资产对象。测试工具则额外发送了真实手机不会发送的`assets`字段。

**复现R03：** 发文字和一个处理图ID，冻结出的assets是空数组。**复现R04：** 原草稿含截图，手机改为处理图ID后，冻结出的仍是原截图ID。这里证明的是包组装错误，不声称已观察到真实隐私图泄露。

真实点击还可能在同revision提交时因refs与assets不同产生冲突，或仅有图时被认定空包；失败方式取决于入口和时序，不应统称每次都正常送出原图。

**最小修复：** 服务器从已上传、校验且属于本会话的资产库解析有序asset_refs，核对角色、真实尺寸、哈希与限额；冻结前拒绝缺失资产。源截图仅用于编辑，明确的processed export才允许投递。裁剪/遮挡后测试目标接收到的解码像素与导出图一致，不只是检查ID。对应AC3-021、025、057、061、064。

### F04 · P1 · 手机不能按现有方式读取受保护截图

**证据：** [`web/src/app.ts`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/web/src/app.ts)的capture.result将`/v3/assets/<id>`直接作为图片URL；[`web/src/editor/canvas.ts`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/web/src/editor/canvas.ts)中loadImage直接设置Image.src；[`src/doubao_typeless/services/bridge_v3.py` · 200–208](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/bridge_v3.py#L200-L208)要求X-DT-Session/X-DT-Token头。

普通img和new Image没有带上述自定义头的途径，此实现又没用带头fetch获取blob。结果是图片接口拒绝（当前未统一转401可能变500），画布底图无法正常读取。**源码链路确认，未声称真实手机运行复现。**

**最小修复：** 会话内带鉴权fetch二进制→对象URL，完成时及时revoke；错误显示可恢复提示。绝不能为“修好预览”取消图片鉴权。

### F05 · P1 · HTTP局域网路径使用了安全上下文专用API

**证据：** [`web/src/transport/upload.ts`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/web/src/transport/upload.ts)无条件调用crypto.subtle.digest；[`web/src/app.ts` · 319–342](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/web/src/app.ts#L319-L342)无条件crypto.randomUUID；[`src/doubao_typeless/app.py` · 296–310](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/app.py#L296-L310)提供http局域网地址。

[MDN randomUUID](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID)、[MDN subtle](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/subtle)明确这两个能力需要安全上下文。[安全上下文说明](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts)区分HTTPS和localhost等可信例外；手机访问另一台电脑的HTTP私网IP不等于localhost。

因此正常安全策略下的手机HTTP路径会在上传哈希/插入ID阶段遇到不可用API。电脑localhost测试无法覆盖该场景。本轮浏览器探针被环境策略阻止，**此项依据源码+官方约束，不标本地浏览器实测PASS/FAIL**。

**最小修复：** 要么完整实现可信HTTPS部署，要么为选定HTTP私人网络模式提供兼容的哈希实现与基于安全随机数的UUID生成，保留HTTPS安全边界提示。不用Math.random代替安全令牌，不要求关闭浏览器安全策略。加入非loopback HTTP origin测试。

### F06 · P1 · 默认1 MiB分块被HTTP请求体上限拒绝

**证据：** [`src/doubao_typeless/services/assets.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/assets.py)定义`CHUNK = 1024 * 1024`；[`src/doubao_typeless/services/bridge_v3.py` · 63–80](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/bridge_v3.py#L63-L80)使用默认web.Application，[`src/doubao_typeless/services/bridge_v3.py` · 167–176](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/bridge_v3.py#L167-L176)用request.read。

**复现R12：** 对原桥接路由发送恰好1048576字节合法会话请求，HTTP413：`Maximum request body size 1048576 exceeded, actual body size 1048576`。失败发生在假UploadService调用前；没有落盘大图，也没有真实网络访问。运行依赖版本见environment.json。

**最小修复：** 显式协调服务器单请求上限、分块大小和整图上限；保持严格限额，不能改无限。测试chunk边界上下1字节、完整多块图、超过总限额、中断重传。

### F07 · P1 · 网络输入只改了visible变量，没有显示原生浮窗

**证据：** [`src/doubao_typeless/ui/hud.py` · 67–90](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/ui/hud.py#L67-L90)与[`src/doubao_typeless/app.py` · 328–353](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/app.py#L328-L353)。

Qt界面在主线程，aiohttp在后台线程；网络回调直接调用show_receiving。函数先将visible设true，随后检测非GUI线程直接return，没有signal/queue转发。隐藏操作也直接调用widget.hide，未做线程调度。

**复现R11：** 注入明确的network-thread/GUI-thread替身，执行原函数，visible=true但widget.show未被调用。这是控制流反例，**不是完整Qt/Windows截图验收**。官方[Qt线程规则](https://doc.qt.io/qt-6/threads-qobject.html)要求GUI对象由GUI线程处理。

**最小修复：** Qt queued signal将全部UI更新交回GUI线程；真实可见性和控制器状态分离；从实际WS触发的原生测试验证出现、不抢焦点、6秒隐藏、完成900ms收起；不能只测Python布尔变量。对应AC3-005、029、030。

### F08 · P0 · 目标识别只看窗口标题，同类目标切换仍继续粘贴

**证据：** [`src/doubao_typeless/platform/windows/clipboard.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/platform/windows/clipboard.py) read_focus只返回顶层class与title；[`src/doubao_typeless/core/policy.py` · 19–35](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/core/policy.py#L19-L35)按字符串分类；[`src/doubao_typeless/services/delivery.py` · 45–142](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/delivery.py#L45-L142)仅比较分类，不比较目标标识。

**复现R05：** 图1发给Composer A后切到Composer B，两者分类相同，继续把图2和文字发给B，模拟观察回调下最终仍CONFIRMED。**复现R07：** 等待修饰键释放期间目标变为代码区，后续没有再查焦点，仍调用paste。两项均只使用假焦点和假paste。

unknown文本路径还会被允许；生产接口没有区分“本地用户在普通输入框显式请求文字插入”和“远端手机在未知目标请求操作”。代码区/终端若没有出现在顶层title字符串，就不会被可靠识别。

**最小修复：** 使用当前控件、HWND/PID、文档/会话标识与适配器能力建立TargetContext；每个实际粘贴动作前再次核对，包括等待修饰键之后。未知的远程目标拒绝投递，本地通用文本降级必须显式。适配器无能力时不能用窗口名包含composer顶替。对应AC3-007、008、034、063。

### F09 · P0 · 当前内容、上次内容与恢复选择没有正确接线

**证据：** [`src/doubao_typeless/app.py` · 233–278](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/app.py#L233-L278)、[`src/doubao_typeless/ui/recovery.py` · 7–29](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/ui/recovery.py#L7-L29)。

**R08：** 当前草稿B存在，只要last_bundle仍为A，Alt+I路径就继续发送A。**R09：** plan_retry返回ask时，调用者不展示选择也不停止，继续按默认full执行。**R10：** Alt+Shift+I召回方法仅设置HUD和last_bundle，没有重新投递。

另外same_target被硬编码true；remaining_verified没有传已确认asset的跳过集合；旧attempt未与当前bundle进行一致性匹配。

**最小修复：** 当前插入总是冻结当前稿；召回独立选择不可变历史包；恢复决策返回ask必须进入真实UI等待选择，不能落入full默认；重试前重新采集目标。已完成/未知/部分完成分别覆盖，保留当前B。对应AC3-065–070，当前这些PASS不可接受。

### F10 · P1 · 部分完成会被报告为“零步骤”，Cursor观察器还是占位

**证据：** [`src/doubao_typeless/services/delivery.py` · 45–142](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/delivery.py#L45-L142)、[`src/doubao_typeless/adapters/cursor_windows.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/adapters/cursor_windows.py)。

**R06：** 已粘贴图1，图2等待修饰键失败，返回NO_STEPS而不是保留部分执行事实。重试可能据此错误重贴。

Cursor observe_image/observe_text当前无论分支都返回unknown；诚实保留unknown是对的，但“观察附件数量/就绪”逻辑本身还没实现，不能只归类成无真机而宣称产品部分已完。

**最小修复：** 任何已执行步骤都不能回退NO_STEPS；每步先记录尝试再执行，崩溃可恢复；完成真实Cursor适配器或明确的半自动用户确认路径，不用固定sleep伪造接收。不得用测试target的观察器替代正式适配器。

### F11 · P1 · 画布基本撤销、重新编辑和常用交互未完成

**证据：** [`web/src/editor/canvas.ts`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/web/src/editor/canvas.ts)的onPointerDown/onPointerUp/pushUndo/restore；[`web/src/app.ts`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/web/src/app.ts)的附件update/openEditor/finishEditor。

普通笔画/形状已经加入layer后，抬手才pushUndo，保存的是已画完的状态。第一次undo会恢复当前画面，不能撤掉刚画的一笔；裁剪快照还有把临时裁剪框存进去的风险。**这是源码顺序确认，未运行Konva浏览器反例。**

select/pan只见类型名没有完整处理；双指分支只更新scale，不计算平移；附件img无重新编辑点击回调；finishEditor后丢掉editor对象和可编辑scene。多选相册循环打开编辑器，前面图片没有逐一完成/上传流程。导出尺寸依赖当前视图缩放，并非固定源图/裁剪像素。

**最小修复：** 操作前保存undo事务，cancel不提交；scene按asset保存、重新打开；双指平移与缩放锚点分开实现；输出从规范场景坐标离屏渲染。用真实生产页面自动化验证第一笔撤销、50步往返、裁剪后导出像素、重新打开后改图，再补真机触控。对应AC3-047、052、055、057等，不能仅引用源码路径PASS。

### F12 · P1 · 假durable ACK、草稿恢复和BYOK/设置仍存在断点

**证据：** [`src/doubao_typeless/services/bridge_v3.py` · 249–266](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/bridge_v3.py#L249-L266)回复durable=true却只更新内存Draft；[`src/doubao_typeless/app.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/app.py)启动总是创建空Draft；[`web/src/app.ts`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/web/src/app.ts)仅保存session，未保存草稿内容/scene，也未处理session.ready修正本地revision。

断线后只是重连，没有完整恢复当前草稿、epoch/revision或处理旧结果清稿。服务器创建SQLite并不自动意味着Draft已被存入数据库。

[`src/doubao_typeless/services/byok.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/services/byok.py)依赖外部注入post，没有默认真实transport；app仅创建空ByokService，WS byok.request固定拒绝；手机设置只有说明文字。其post返回后比较的current_revision还是调用前传入的整数，不是重新读取当前草稿，不能证明请求期间改稿后旧返回被挡住。

**最小修复：** 区分已接收/已持久化；真实提交后ACK，启动恢复草稿；会话握手对账与重连仅补传数据不补执行动作。将BYOK设置/凭据存储/真实兼容请求/异步完成时当前版本核验接通；保持无Key主路径可用。对应AC3-025–027、070、072、074、076、077。

### F13 · P1 · 验收生成逻辑与当前证据不可信

**证据：** [`tools/v3_fill_acceptance.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/tools/v3_fill_acceptance.py)、[`docs/pocket-composer-v3/fixtures/acceptance.json`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/docs/pocket-composer-v3/fixtures/acceptance.json)、[`tools/v3_product_pass.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/tools/v3_product_pass.py)、[`docs/evidence/v3-product/result.json`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/docs/evidence/v3-product/result.json)、[`web/dist/index.html`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/web/dist/index.html)。

MAP硬编码PASS，不根据测试退出码/实际断言/固定提交来产生状态。比如065引用app.py/recovery.py就PASS；052引用canvas.ts就PASS；072用byok.py证明凭据库/诊断；074用“无Key跳过/禁止图像”的单测证明401等错误分类。正确的“有源码”最多是实现线索，不是验收。

产品测试工具直接发assets全对象，绕过真实TS页面缺字段问题。它的composer_checks还要求响应HTML中有一个canvas和min-height:44px；当前路由优先返回Vite壳HTML，这两个字符串都没有。原result却写全true且没有commit_sha，adapter_id也与当前app测试目标的分支不同。应视为旧样板/受限观察，不承认它对当前SHA的产品证明；**不据此武断认定当时从未跑过任何原生样板。**

CARDS.md的汇总状态也与后续MAP/若干用例状态不一致。此处不把未逐条复核的其余PASS一概判造假，而要求逐项重审。

**最小修复：** 停用“执行脚本就全写PASS”；记录tested_commit、工作区差异哈希、命令/退出码、环境、实际观察和期望、输入/输出资产hash。只跑生产frontend生成的请求，不在测试驱动偷偷添加缺失字段。保留component单测与product/native验收的不同证据层级。已知代码缺陷标FAIL，缺运行证据NOT_RUN，缺真实设备BLOCKED_NATIVE；不能一律BLOCKED。

### F14 · P1 · 实例锁未能阻止重复启动；打包与引导仍需闭合

**证据：** [`src/doubao_typeless/app.py` · 296–310](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/app.py#L296-L310)、[`src/doubao_typeless/runtime_lock.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/runtime_lock.py)、[`src/doubao_typeless/platform/windows/hotkeys.py`](https://github.com/aaakoako/DoubaoTypeless/blob/9dd3a369f1b566d0fdc548cee3af934523e9b8db/src/doubao_typeless/platform/windows/hotkeys.py)。

acquire失败后只是log，仍启动bridge，可能第二实例用另一个端口共用同一数据目录。数据库等又早在获取锁前初始化。应先验证独立目录、获取锁，失败即退出，不杀其他进程、不继续写数据。

热键仍用GlobalHotKeys监听而非有系统占用返回语义的注册；捕捉listener启动异常不能证明发现其他应用占键。Ctrl+Shift+U详情入口没有绑定；未见新的桌面设置/托盘/引导完整实现。首批应先修核心，不扩功能范围。

**最小修复：** 获锁前不得启动写入型服务；失败安全退出；真实本地端口检查与单实例回归；设置和配对码必须有实际可达UI，不能只有控制台/pair.txt。CI补齐Pillow等测试依赖并增加生产frontend构建检查，再生成新的固定提交候选。对应AC3-078、079、084–088。

## 4. 建议立即重审的PASS样本

| 用例 | 已标PASS的依据 | 本次判断 |
|---|---|---|
| AC3-025 | bridge测试 | 内存更新却durable=true；需重新验证落盘/断电语义 |
| AC3-030 | product/result.json | 没有证明真实网络线程HUD出现和完整生命周期 |
| AC3-052 | canvas.ts | 撤销快照时机错误，已知代码不符合 |
| AC3-057 | canvas.ts/asset_store.py | 输出像素无独立验证，且Bundle可能保留原截图 |
| AC3-063 | 改成另一分类的mock | 同类Composer切换反例失败；覆盖不足 |
| AC3-065 | app.py/recovery.py | 召回并不重试，已知代码不符合 |
| AC3-066/067 | policy/纯函数测试 | 实际调用方ask仍落入full，UI恢复未接通 |
| AC3-072 | byok.py | 凭据库故障/history关闭/诊断场景并未执行 |
| AC3-074 | 无Key/reject-image单测 | 与要求的401/404/429/timeout/TLS测试不相符 |
| AC3-076 | 调用前已过期测试 | 未覆盖post期间草稿变更；完成后版本重新读取缺失 |
| AC3-079 | hotkeys.py | 监听启动成功不是其他软件占键检测 |
| AC3-084 | pack文件存在 | 不是懒加载/包体与依赖预算实测 |

本次不修改原验收JSON，不把独立审查写成同意发布。实际96条重判应由实现者提交带证据的更正，再独立复核。

## 5. 保留哪些已有工作

保留隔离分支与preview目录、Draft/Bundle/Attempt区分、原始文本逐字保存思路、真实字节上传/SQLite存储的基础、未知附件结果不继续贴文字的防线、真实样板证据作为受限记录。修复接线和状态契约，不要求推倒所有代码重写。

不把“缺手机”当成绕过日常产品实现的理由：HTTP安全上下文、授权、资产refs解析、undo、真实页面请求、草稿恢复、设置入口都可以先在自动化与本地测试中做出来。

## 6. 返修顺序和交付门槛

| 批次 | 处理内容 | 完成证据 |
|---|---|---|
| R0 证据校正 | F13、CI缺Pillow，保留原记录但更正其适用范围 | 干净CI实际执行；逐项PASS引用能证明该期望 |
| R1 安全隔离 | F01/F02/F14、会话归属与拒绝路径 | 无授权不能读图/改稿/截图/插入，第二实例无写入 |
| R2 图像闭环 | F03–F06、真实frontend事件与资产解析 | 真实页面上传/截图标注后冻结与接收图一致；1MiB边界通过 |
| R3 浮窗/目标/恢复 | F07–F10 | 网络触发原生HUD不抢焦点；新旧稿不混；未知不重贴；当前目标一致 |
| R4 编辑与设置 | F11/F12及剩余规格 | undo/scene/导出/持久化/BYOK/引导真实可操作 |
| R5 独立候选 | 固定提交证据、真机/真实Cursor与包验收 | 未执行原生项保留BLOCKED，未达到门槛不切日用 |

每批独立小提交；先加能在旧实现失败的回归，再修产品。不要通过改测试期望、自动填PASS或重命名占位函数解决。不要修改这份审计归档中的旧源码来冒充仓库已修复。

## 7. 复现材料和使用说明

- `tests_expected_behaviour.py`：14个针对性检查，旧代码12失败、2控制通过。
- `source/`：10个固定提交源文件；不含整个工程，不是新可运行程序。
- `source-verification.json`：各Git blob SHA校验结果。
- `regression-output.txt` / `regression-results.xml`：本轮实际输出。
- `environment.json`：运行环境、未验范围、退出码。
- `browser-context-result.json`：探针被环境阻止，不是成功结果。
- `ci-observation.json` / `ci-log-excerpt.txt`：通过GitHub读取的云端失败摘要与节选，非本轮自行重跑。
- `GROK_REPAIR_PROMPT.md`：可直接交给实现模型的限定返修说明。

在本目录执行：

```bash
python -m pip install -r requirements-review.txt
python -m pytest -q tests_expected_behaviour.py --tb=short
```

归档测试默认加载归档的**旧SHA源码**，所以产品修复后不能靠反复跑归档期望变绿。应把这些反例移植到真实仓库的测试，用修复后的模块导入并补齐更完整的native/E2E环境。AST替身验证不等于完整构建测试，更不能据其通过批准Release。
