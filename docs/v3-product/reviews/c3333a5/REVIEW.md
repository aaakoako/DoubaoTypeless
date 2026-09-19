# DoubaoTypeless V3 复核：c3333a5 / 69eb4f8

**日期：2026-09-19　结论：REQUEST_CHANGES；已有明显进展，但不是仅剩 A18 真机。**

本报告是对现有 `docs/v3-product/MASTER_PLAN.md` 的执行复核，不改变产品范围、不另起新方案。继续保留旧版顺手的文字输入、插入并复制、收窗、新稿与历史恢复，并完成手机图文。

## 1. 提交和工作区边界

- 远端 `origin/v3/00-baseline`：`c3333a55a516022397772eea932c8a21c7a26cd0`。
- 产品提交：`69eb4f875be0fea1ab12cce7b1e0d36f40d81b34`。
- 实际比较 69eb4f8 → c3333a5：只修改 `docs/v3-delivery/CHECKPOINT.json`。运行产品代码相同，不能仅因 HEAD 不同就说包源码过期。
- 与上一轮固定复核 `8326bb475707cc4d3f2948379b67a5397226709e` 比，新增 7 个提交。
- 本轮没有访问用户电脑本地 Git 工作区，不能独立证明其工作区 clean。上述为远端已推送提交事实；CHECKPOINT 的 clean 是实现者记录。
- 没有远端写入、push、merge、tag、Release，没有操作日用安装或用户预览进程。

## 2. 真实进展：允许关闭的是具体子问题

| 原发现 | 本次已确认的进展 | 本次结论范围 |
|---|---|---|
| A15 / F02 CI与HTTP | Linux补Qt系统库；增加Windows测试；真实CI三项job均success | CI失败这一子问题可以关闭；不等于全产品PASS |
| F02 GET/图片SHA | GET/HEAD不再因缺Origin被一刀切拒绝；上传没有subtle时不再直接抛HTTPS错误 | 旧的两个直接阻断已有源码修复；HTTP仍非加密链路 |
| F01 插入入口 | 手机与电脑当前插入共同进入deliver_and_finish | 入口收尾合并了，但手机事件生成/分发/消费仍有R01 |
| F03 编辑失败 | finishEditor清旧asset_id，上传失败不沿用它 | 该局部失败分支修复；电脑仍可能持有旧原图，见R04 |
| F05 区域截图 | capture_region现在向_on_capture传入会话 | no session调用遗漏修复；向正确手机推送结果还需端到端验收 |
| F07 修饰键 | 等待修饰键后增加焦点复核，已贴过图的失败不再回报NO_STEPS | 旧两个代码反例的触发点已修；目标身份仍是另一子问题 |
| F08 剪贴板 | CLIPBOARD_INTERFERENCE结果不再无条件写回旧文字 | 旧报警后回写子问题修复；完整剪贴板并发仍要回归 |
| F09 密钥失败 | 正常凭据库失败回内存，只有显式测试开关才用文件后端 | 旧默认明文回落子问题修复；不签整个凭据体系通过 |
| A03 长文 | QTextEdit可滚动、正文与按钮分行、固定400宽和300上限；hide跨线程有context | 不是仅改常量了；阅读中停追尾/停隐藏仍没完成 |
| A09 / A13 | 记住设备服务、逐图排队、页签下划线/hover、历史选择保留 | 不是空工作；具体流程缺口见后文 |

### CI事实

[Actions run 35447748147](https://github.com/aaakoako/DoubaoTypeless/actions/runs/35447748147)，固定HEAD为c3333a5。

| job | id | 读取结果 |
|---|---|---|
| windows-pytest | 105909514688 | completed / success |
| pytest（Ubuntu、前端typecheck/build） | 105909514757 | completed / success |
| windows-min-pack | 105909649175 | completed / success；制品上传步骤success |

这是本轮读取的GitHub实际结果，不是把CHECKPOINT的“177 passed”当成独立验证，也不沿用上一轮libEGL失败。Windows job名字包含native不等于真实Android、Cursor或所有用户点击流程已执行。

## 3. 必须继续修的发现

### R01 · 阻断 · 完成回执仍会漏清旧稿、误清新图；本地热键没有主动送达手机

**对应 A02/A12、上轮F01。**

证据：`app.py::_on_intent/_maybe_start_next_draft/_phone_rotate_event/_after_insert`；`bridge_v3.py::_handle(insert.intent)`；`web/src/app.ts::draft.rotated`。

1. CONFIRMED在_on_intent里归档电脑稿，随后_maybe_start_next_draft对CONFIRMED直接返回False。最终phone_event.archived为null。手机用archived.text匹配，已确认投递的非空文字不会被清掉，却被换到新epoch。
2. 图片-only、结果UNKNOWN或失败时，archived也为null；手机把它当作空文字。当前图片-only稿的text也是空串，same为真，因此清掉整个附件列表。它不是已确认成功，不能当正常新稿。
3. 即使有archived，手机仅比较正文，不比较draft_id、epoch、revision、附件或hash。插入A期间新加图片B但没有改说明，旧回执会删掉B。
4. 本地Alt+I只设置bridge.last_phone_event并通知桌面隐藏，WS发送事件仍只发生在手机insert.intent分支。没有看到向已绑定来源手机主动推送该本地结果的调用；也没有该最后事件的结果查询接口。统一回调不等于所有入口都把回执送到手机。

**本轮反例：**phone-events四个失败中的前三个证明1–3。它们运行原事件分支，不是浏览器真机，不能扩大为实机录像。

**最小修复：**让唯一完成服务输出明确的`rotated`与匹配旧稿身份；生成结果前后只轮换一次。所有入口经同一发布器向绑定来源会话发送/供查询，不靠手机再次点击才取到结果。客户端先匹配身份、版本、正文与附件版本，再应用新稿。UNKNOWN/失败的图片保留。不要用空archived当空稿，不通过把UNKNOWN改成CONFIRMED修体验。

**验收：**Alt+I/浮窗/详情/手机四入口分别执行A/B/C；CONFIRMED文字、UNKNOWN纯文、UNKNOWN纯图、图文部分完成；A期间加图B或重排附件；重复旧回执、晚到回执、新epoch。核对真实手机DOM和附件，不只测电脑draft空串。

### R02 · 阻断 · 重连会把旧缓存换成新身份，再自动覆盖电脑新稿

**对应 A12、上轮F04/F12。**

`session.ready`先计算身份是否相同，然后无条件把手机draft_id/epoch/revision改成服务器的值。如果之前不同且手机有内容，就sendDraft。sendDraft又增加revision。

所以旧缓存A不是被识别为旧稿并等待选择，而是被重新标为服务器的新稿身份和更高版本，再发回。后端这次虽然去掉了max(revision,current+1)，前端仍能在重连时把保护绕掉。

另外，`bundle.commit/insert.intent`消息仍不带draft_id/epoch；后端对缺少身份的消息仍可受理。`draft.ack`包含parked/durable/error时手机也一律提示“电脑已收到”，没有真实对账。

**反例：**手机E1缓存A，session.ready给E2/rev20，原分支会立即调用sendDraft，而非进入冲突选择。

**最小修复：**连接握手取得服务端完整摘要/必要正文；旧本地稿与新服务端稿分别保留，明示恢复或合并，不直接改身份并重发。所有写入和插入意图必须绑定明确稿件/版本，接收端拒绝旧身份。ACK需要按事实处理，不得把parked或error提示成已同步。

**验收：**手机离线A→电脑完成/开始B→恢复前台；服务重启、刷新页面、相同文字不同稿、断线期间新加图；B不能被A替换。

### R03 · 阻断 · 记住设备服务有了，但首次记住/失效续接/撤销还没形成一致流程

**对应 A09/A17。**

#### 3.1 记住凭据没有在正常点击时送达

手机只在session.ready调用一次`pullRememberedSecret()`。一般顺序是手机先连接，电脑随后勾选“记住设备”。勾选调用remember_connected/remember_device，生成secret后只改桌面文字，没有向手机发送通知、凭据或让它重新拉取。因此手机第一次握手时取到的可能是空值，后来没有再取。

还存在旧会话失效：页面只要sessionStorage里有session就connect；服务器重启或过期后session.hello会被拒绝，前端error只toast，不清旧session、不转resumeRemembered。resumeRemembered只在页面初始没有session时执行。不能把AuthService方法能resume视为完整用户流程通过。

#### 3.2 撤销设备没有撤销它的其他有效会话

resume_trusted每次新增Session，不淘汰旧Session。`revoke(session_id)`只删除一个会话与trusted记录；其他属于同一device_id的Session仍在sessions中并可通过authorize。set_grants也只改指定会话和trusted，不更新其他现有会话。

**本轮原模块执行：**先配对并授权、记住、resume获得第二会话，撤销第一会话后第二会话仍通过capture；关闭第一会话截图许可后第二会话仍通过capture。对照：被直接撤销的会话会拒绝，重启AuthService后从持久化trusted恢复也会成功。这说明不是整套记忆功能完全没做，而是跨会话失效规则缺失。

`_toggle_remember`取消勾选直接return，也没有对应忘记设备语义；重复remember会刷新secret，若手机没有收到新值会再次失配。

**最小修复：**桌面明确记住动作与手机确认保存组成同一交接；凭据交付可靠且不公开广播。鉴权失败有可判别错误码，清除过期session后尝试已记住凭据，失败再配对。权限以设备记录为权威或遍历失效同设备所有会话并关闭对应WS。支持明确“忘记设备”，重复勾选不能无提示毁掉现有凭据。

**验收：**正常扫码→连接完成后勾选→不刷新也保存→重启电脑→手机原标签自动恢复；新标签产生第二会话后撤销/关截图，两条连接及后续resume都符合许可；令牌不能出现在普通日志/诊断。

### R04 · 阻断 · 图片逐图排队改进了，但源图/编辑中/成品仍没有统一投递门槛

**对应 A07/A12/A17、上轮F03/F12。**

- `finishEditor`现在上传失败清asset_id是正确修复。但清ID发生在点完成之后。手机编辑期间电脑草稿仍保留先前已上传图/原截图；`editor.activity`只触发显示，不建立不可投递的dirty版本。
- `_on_capture`仍直接把原截图加入`draft.assets`。手机正在遮挡或裁剪时，电脑Alt+I可以冻结这个原图，不受手机的assetRefs检查保护。
- 队列里的截图最初也有asset_id，assetRefs仍只检查ID是否存在，没有检查queued/editing/failed状态。
- 新增captionInput、caption字段保存了说明，但sendDraft/insert.intent只传state.text和asset_refs；caption没有合并为说明，也不进入服务端图文合同。因此用户在标注页补的说明可能没有投递。

**最小修复：**图片文档标识、源图、编辑版本、已完成成品分离；编辑开始就向服务端声明脏版本，所有投递入口验证所有选定图是当前版本的已完成成品。原截图只能先是编辑资源，不得默认为投递成品。caption有可预览、明确的发送规则，不偷偷改正文也不无声丢失。

**验收：**原图含测试保密区→手机开始遮挡但还没点完成→电脑Alt+I必须被拦；原图重新编辑失败、两张图第二张未完成、补充说明随后投递，核对实际图像和文本。

### R05 · 阻断/重要 · 场景重开恢复没有恢复底图；本地持久化仍只保存失效URL

**对应 A07/A12、上轮F12。**

当前openEditor对有scene的普通照片也调用importScene，这是试图恢复编辑对象的进步。但`canvas.ts`本轮未改：exportScene用Konva.toJSON记录节点；importScene用Node.create恢复。没有重新加载图片像素并绑定图片节点。

Konva官方明确图片对象和事件不可序列化，Node.create之后必须自己重新设置：
https://konvajs.org/docs/data_and_serialization/Complex_Load.html

有scene分支不再走loadImage；恢复后可能只有标注而没有原照片。白板背景是可序列化图形，不可用白板成功证明照片成功。

persistDraft保存scene/source/preview字符串，但相册source和未完成preview是blob URL，而不是图片字节；刷新后的生命周期无法靠这串URL恢复像素。已上传preview也直接设为受保护GET地址，缩略图img.src没有相应带鉴权加载。

另外canvas普通笔画完成后才pushUndo的旧结构仍在；双指分支仍只改scale，没有平移实现。新增队列测试不能关闭整个白板手感/撤销范围。

**最小修复：**显式保存可恢复源资产（受鉴权的服务端引用或IndexedDB Blob），重建scene后绑定像素再ready；待上传素材也能恢复，不吞配额错误。撤销快照在动作前保存；缩放平移与裁剪恢复分别测试。

**验收：**照片画箭头→完成→重开→移动箭头，底图和对象都在；刷新/断网待传图恢复；第一笔撤销、裁剪后恢复全图、双指平移。包含测试色块的像素检查，不只是scene字符串存在。

### R06 · 阻断 · AI异步与过期保护仍会覆盖用户新稿

**对应 A10/A12/A14、上轮F10。**

有改善：suggest_rewrite把请求放线程；增加可见建议文字和before_apply。

但：
1. suggest_text在请求返回后读取当前稿身份写进_last_suggestion，而不是请求开始时固定身份。请求期间换稿会把旧结果标成新稿的建议。
2. apply_suggestion只检查draft_id/epoch，忽略revision和原文是否仍相同。用户在同一稿继续改字后，旧建议依然能覆盖。
3. reject_suggestion恢复before_apply时只匹配draft_id，不匹配epoch。start_new_draft保持draft_id、只换epoch，因此旧建议“撤回”能把上一段文字写进下一段。
4. ReviewPanel.reject_rewrite没有把恢复后的正文写回编辑框。界面还显示建议，下一次点插入又写回建议，撤回没有端到端生效。
5. 新线程回UI使用无context的QTimer.singleShot(0, apply)，不是可靠的Qt主线程投递；probe_byok仍同步执行请求。保存的byok_timeout也没有接到app.byok的有效超时参数。

**本轮反例：**同稿rev10建议覆盖rev11新编辑；E1已采用建议的撤回覆盖E2新稿。均执行原方法体，无真实API调用。

**最小修复：**请求开始前冻结稿ID/epoch/revision和原文，返回后读当前状态核对；采用/撤回匹配精确可撤销版本，界面/数据一起更新。主线程QObject信号或有context回调，probe与正文共用非阻塞通道。真实超时参数生效，不仅存表单。

Qt线程约束参考：https://doc.qt.io/qt-6/qtimer.html

**验收：**慢响应期间改字、插入、换稿；同文本不同稿；采用后继续编辑再撤回；UI文本、持久化和插入内容三者一致。模拟API允许用于故障测试，不能据此签真实服务兼容。

### R07 · 仍需开发与验证 · 真实目标和恢复还不能全归到设备

**对应 A04/A05/A06/A18。**

等待后的复核和PARTIAL修复应保留。但Windowsread_focus仍只提供顶层class/title；同名窗口、同窗口多个编辑控件没有具体指纹。`insert_last`仍写same_target=True，已确认部分图片的跳过集合没有绑定同一个目标、同一Bundle实际尝试。删除replay_snapshot清_last_attempt是改善，但读取的仍可能是另一个包最近尝试，不能以此关闭历史包/尝试对应关系。

Cursor附件观察器在本次对比中未修改，上轮函数最终仍返回unknown。没有设备的实测确实属于阻塞，但实现一个永远unknown的观察器本身也不是已完成可验证功能。

**修复：**目标上下文和每个包的尝试记录真实绑定；进入恢复选择时重新读取目标，同包同目标有证据才补剩余。主支持目标的附件观察要真正实现并在对应环境测试；不能用定时sleep或把UNKNOWN改成功替代。

### R08 · 仍需完成 · 产品界面与候选包状态不能仅列A18

- HUD已换滚动正文和独立按钮行，这部分值得保留；但每次更新仍setPlainText并重新开始6秒timer，没有阅读前文/选择文字时停追尾和停隐藏。
- 原生页签hover、选中下划线已写入样式，历史刷新保留选择，是进步。本轮没有运行新Windows包，没有签整个视觉符合UI_BOARD。
- ReviewPanel仍常显一整行八个按钮；情境分层和主次操作未完成。关闭面板释放editing已修，但未保存的电脑修改在hide后被下次reload覆盖的问题需从实际入口回归。
- CHECKPOINT注明本切片改源码与前端，旧A03窗口包未重新打包，却把candidate_artifact.source_sha指向69eb。旧哈希不要继续与新source_sha放成一条可追溯候选。另设旧包记录与待构建新候选。
- 本轮CI确实打出了c333的最小包，不能再说完全没打新包。但workflow构建`packaging/v3_preview.spec`，不是`v3_preview_windowed.spec`，也没有证明用户当前本地正在跑的包已更新。
- Windows打包job的needs只有pytest，不包含windows-pytest；作为开发包可以早出，正式候选应同时依赖所需平台检查，避免以后Windows测试失败仍生成貌似可发布制品。

## 4. 本轮实测与限制

### 已执行

1. 完整credentials.py从GitHub读出后写入审阅目录，按Git blob算法核对：`5389461abb773d210fab7df93227d04bc7bc6b5b`一致。
2. Python：6项预期行为测试，**4 failed / 2 passed**。两项失败来自真实AuthService多会话失效；另两项执行app建议方法摘录。
3. Node：5项事件分支测试，**4 failed / 1 passed**。仅去掉TypeScript类型断言，把原事件分支包装成可调用函数，使用模拟DOM/WS动作，无修改分支逻辑。
4. 实际读取GitHub三项CI job成功状态；不把CHECKPOINT测试数当独立运行结果。

这些是为疑似缺陷定向编写的反例，不是产品通过率，不是原仓库177项测试。对照组能证明设备记录可持久化恢复、直接撤销指定会话有效、匹配普通文本回执可轮换；不是说所有功能全坏。

### 没有执行

本地完整clone因DNS不可用失败；codeload下载没有获得可用归档。没有运行完整仓库测试、完整生产浏览器流程、Windows EXE、Android/豆包、Cursor或真实剪贴板。没有重新计算用户本地包哈希。源片段运行明确不是整应用验收，图片再次编辑问题依据源码和Konva官方合同而非本轮实机截图。

## 5. 返修方式：不另起V4，不只改状态

继续现有MASTER_PLAN，按R01–R08映射重开相关A项。保留已经修好的具体子项和这次CI成果，不恢复过期失败。

内部实施顺序：

1. 统一稿件身份、完成事件及消息交付，先补四入口A/B/C和失败纯图；修重连旧稿回放。
2. 记住设备的真正用户流程与同设备所有会话失效。
3. 服务端图片编辑/成品门槛、照片scene恢复、图片字节持久化、caption投递。
4. AI请求身份/撤回与GUI线程；完成HUD阅读态和审阅按钮分层。
5. 同包同目标恢复与真实适配；用最新源码重建完整无控制台包和manifest。

每个步骤回归后继续下一个可执行工作，不要求用户逐张卡说继续。设备不足只阻塞对应手感/目标验证，已知代码失败仍继续开发。不要删除测试、降低期望或更新旧证据文本来制造通过。

交付时先演示：四入口连说三段、新图不误清、重新打开手机自动续接、照片再次编辑底图不丢、撤销许可立即生效、慢AI不覆盖新文。然后再附测试数和包哈希。

## 6. 固定源码来源

下面所有链接固定在本次HEAD；方法名用于定位，不为未展开内容编造行号。

- [src/doubao_typeless/app.py](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/src/doubao_typeless/app.py)
- [src/doubao_typeless/services/bridge_v3.py](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/src/doubao_typeless/services/bridge_v3.py)
- [src/doubao_typeless/storage/credentials.py](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/src/doubao_typeless/storage/credentials.py)
- [src/doubao_typeless/storage/secret_store.py](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/src/doubao_typeless/storage/secret_store.py)
- [src/doubao_typeless/services/delivery.py](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/src/doubao_typeless/services/delivery.py)
- [src/doubao_typeless/ui/desktop.py](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/src/doubao_typeless/ui/desktop.py)
- [src/doubao_typeless/ui/hud.py](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/src/doubao_typeless/ui/hud.py)
- [web/src/app.ts](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/web/src/app.ts)
- [web/src/editor/canvas.ts](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/web/src/editor/canvas.ts)
- [web/src/transport/upload.ts](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/web/src/transport/upload.ts)
- [.github/workflows/preview-v3.yml](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/.github/workflows/preview-v3.yml)
- [docs/v3-delivery/CHECKPOINT.json](https://github.com/aaakoako/DoubaoTypeless/blob/c3333a55a516022397772eea932c8a21c7a26cd0/docs/v3-delivery/CHECKPOINT.json)
