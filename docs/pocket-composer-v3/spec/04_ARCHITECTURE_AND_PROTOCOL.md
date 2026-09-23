# 04 · 工程拆分、数据模型和协议合同

## 1. 技术选择与迁移策略

**桌面：Python + PySide6 Widgets。手机：TypeScript + Vite + Konva。网络：保留aiohttp。持久化：SQLite + 受限本地资产目录。** 不引入Electron、Qt WebEngine、React、大型白板SDK或Node后台服务。Node只在构建时把手机资源编成静态文件，由Python提供。

这是针对“桌面极简、复杂交互在手机”的新范围调整，不是宣称Widgets一定比QML更省内存。PySide6 Widgets提供原生窗口/剪贴板/屏幕接口；手机Konva提供可编辑图形与绘制基础，移动手势仍需自行按规格实现。[S07][S09][S10]

保留CustomTkinter作为G0未通过时的短期基线，**不是同时维护两套新UI**。G0先原生验证，成功后迁移生产入口；不做一次性全工程改名。版本必须在G0实际安装/运行后锁定，文档不给未验证的“最新精确依赖版本”。

Qt GUI/剪贴板/窗口操作在主线程；aiohttp在一个有生命周期管理的后台asyncio线程；所有跨线程事件通过有类型的Qt Signal/queued connection。OS观察/图片处理放工作队列，UI不能同步等待网络或导出。退出顺序：拒绝新intent→停止插入→释放修饰键→关闭WS→提交DB→停止托盘/线程。

## 2. 拟新增目录（不是仓库已有文件）

```
src/doubao_typeless/
  app.py                     # 装配，不写业务分支
  core/{draft,bundle,events,reducer,attempt,policy}.py
  services/{bridge,assets,capture,delivery,history,terms,byok}.py
  storage/{db,asset_store,migration,credentials}.py
  platform/base.py
  platform/windows/{focus,clipboard,keyboard,capture,hotkeys}.py
  adapters/{base,cursor_windows,generic_text}.py
  ui/{hud,detail,pairing,settings,viewmodel,tokens}.py
web/
  src/app.ts
  src/composer/{draft,ime,attachments,sync}.ts
  src/editor/{document,tools,gestures,crop,undo,export}.ts
  src/transport/{protocol,assets,connection}.ts
  src/ui/{composer,editor,recovery,settings}.ts
  src/styles/{tokens,composer,editor}.css
  public/icons/              # 仅审核许可的图标
  dist/                      # CI构建产物，不手工编辑
contracts/                   # 版本化JSON schema
tests/                       # 实际项目根目录下测试
```

旧main.py先保留为兼容入口。旧bridge.py迁移协议而保留可测试的无GUI网络层；旧typer.py拆出Windows适配；gui.py的日志/历史能力按需迁移而不是复制整个大类；phone.html最终成为编译资源入口；polish.py旧学习流程不初始化；config.py做只读迁移而非覆盖旧数据。

## 3. 核心对象

| 对象 | 关键字段 | 不变性/目的 |
|---|---|---|
| DeviceSession | device_id、session_id、capabilities、expiry、last_seen | 凭据只在传输层，业务日志不可含token |
| Draft | draft_id、epoch、revision、editor_device_id、text、ordered_asset_refs | 手机拥有写租约；每次已提交文本/附件版本+1 |
| ImageDocument | asset_id、source_size、crop、objects、undo_version | 手机可编辑场景；原始坐标，不保存DOM |
| RenderedAsset | asset_id、render_revision、sha256、mime、size、width、height | 二进制校验完成后才可引用，文件路径由服务端生成 |
| DeliveryBundle | bundle_id、draft identity、text、ordered_assets、manifest_hash | 冻结后只读；重试复用同一份 |
| TargetContext | HWND、PID、process_start、adapter、focus identity、observed_at | 内存态短命；重试重新采集，日志不存敏感窗口标题 |
| InsertIntent | intent_id、bundle_id、session_nonce、trigger、recovery_mode | 显式用户动作；一次性、10秒有效 |
| DeliveryAttempt | attempt_id、bundle_id、target fingerprint、step journal、result | 多次Attempt可指向同一Bundle，不覆盖旧记录 |

Manifest哈希：UTF-8编码的规范化JSON（键排序、无多余空白、明确Unicode和换行策略）；文字不做NFKC或trim。哈希覆盖图片顺序、渲染版本和每张图片实际SHA256。本包固定算法见contracts/README.md，金标准字节见fixtures/manifest.canonical.json；不能Python/JS各凭默认JSON序列化。

## 4. WebSocket只传小消息，HTTP传图片

协商子协议`dt.v3`。所有WS消息包含`protocol=3,type,message_id,session_id`；连接凭据不写在URL查询串。服务端从已鉴权连接赋值device_id，拒绝客户端冒充。单帧最大256KiB、文字64KiB，类型未知返回可理解错误而不是尝试执行。

| 消息 | 方向 | 语义/必需字段 | 是否可重复 |
|---|---|---|---|
| session.hello / ready | 双向 | 版本、能力、server_boot_id、已存draft游标 | 可，不能触发插入 |
| draft.update | 手机→电脑 | draft_id/epoch/revision/text/asset_refs、is_composing | 最新完整快照；旧版本忽略，同版不同hash拒绝 |
| draft.ack | 电脑→手机 | 同版hash、durable=true/false、缺少asset列表 | 收到ACK才能显示电脑已收到 |
| editor.activity | 手机→电脑 | draft_id、kind、不含笔画正文 | 2秒最多一次，唤醒HUD但不代表数据持久化 |
| asset.ready | 电脑→手机 | id/render_rev/hash | 图片校验并保存完成 |
| capture.request / result | 双向 | request_id、授权scope、结果asset引用 | 一次性，15s过期，无自动重放 |
| bundle.commit / ready | 双向 | frozen manifest，服务端验证资产完整 | 同manifest幂等；缺图拒绝ready |
| insert.intent / attempt.status | 双向 | 一次性意图；步骤阶段与结果 | 重传只查已有状态 |
| draft.archive | 电脑→来源设备 | 匹配draft identity+bundle hash | 仅匹配稿归档，绝不广播无条件clear |
| ping / pong | 双向 | 序列/时间 | 心跳不得导致HUD出现 |

文本更新防抖80ms（上限每秒15次），compositionend补发同文最终标记，客户端不把停顿当成“麦克风停止”。服务端流控超限合并最新草稿，不能合并/重排不同insert.intent。最终提交时发送完整文字，防止遗漏尚未发出的80ms尾巴。

## 5. 二进制资产HTTP接口

```
POST /v3/assets/init
PUT  /v3/assets/{upload_id}/chunks/{index}
POST /v3/assets/{upload_id}/complete
GET  /v3/assets/{asset_id}/render/{revision}
DELETE /v3/assets/uploads/{upload_id}
```

init带期望MIME、总bytes、SHA256和图像尺寸；服务端分配不可猜的upload_id。块大小1MiB，最多并发2个；先stream写临时文件并累计大小再校验，不一次读入无上限body。complete核对总哈希、魔数、解码尺寸和实际像素预算，失败删除临时文件并返回明确错误；只有完成后写入资产表。

断点续传按缺失块列表恢复；旧render_revision上传结束不能替换新图。下载要求同设备/会话授权与所属草稿，不能知道asset_id就任意取图；响应no-store、禁止外部Origin。HTTP鉴权方式、Cookie/CSRF和WS鉴权详见安全章节；文件名永远不当作路径。

## 6. 数据落地与一致性

SQLite保存devices、drafts、bundles、bundle_assets、attempts、attempt_steps、migrations；图像存本应用数据目录随机/哈希文件名。先写临时资产→校验→原子rename→DB事务挂引用；失败不得发送durable ACK。垃圾回收只清理无引用且超过TTL的资产，正在导出/上传/Attempt引用的资产不得清理。

需要重启可召回时，图文快照、步骤和图像必须持久化一致。隐私模式关闭磁盘保存则durable=false且会话内可恢复，不能仍展示“重启后可恢复”。磁盘满时停止接收新大图，手机保留未同步草稿；不能先清空手机再发现磁盘写失败。

电脑详情编辑文字会创建desktop分支修订并暂停手机覆盖，显示“手机有更新”。首版不做复杂协同算法：用户显式保留电脑版/采用手机版。画布仅手机编辑，避免两端多主冲突。编辑上次内容是新draft_id，不与旧版本共享清空事件。

## 7. 有边界的服务接口

CaptureService只执行枚举过的scope ID，不接受网络传入任意Win32句柄。
DeliveryService只收Bundle+Intent，不收任意按键序列/脚本/鼠标坐标。
FocusAdapter只返回VERIFIED_COMPOSER/VERIFIED_TEXT/UNSUPPORTED/UNKNOWN，不用“概率0.9”偷过验证。
HistoryService明确区分copy_to_new_draft、replay_bundle、delete，不以“恢复”含混三种副作用。
ByokService只处理用户这次选择的文字，不读取截图/历史/窗口内容；网络出口只允许已确认配置的endpoint。
