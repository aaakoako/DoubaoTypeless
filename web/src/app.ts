import { SharedEditor, type Tool } from "./editor/canvas";
import { applyReady, applyRotated, buildDraftUpdate } from "./sync.js";
import { looksLikeKeyScript, newId } from "./transport/protocol";
import { uploadPng } from "./transport/upload";
import { DraftRepository, type SavedDraft } from "./storage/drafts";

type Session = {
  session_id: string;
  token: string;
  device_id?: string;
  allow_insert?: boolean;
  allow_capture?: boolean;
};
type AssetStatus = "queued" | "editing" | "ready" | "failed";
type Asset = {
  id: string;
  kind: string;
  preview: string;
  asset_id?: string;
  w?: number;
  h?: number;
  scene?: string;
  source?: string;
  caption?: string;
  status?: AssetStatus;
  render_revision?: number;
};

export function boot(root: HTMLElement): void {
  root.innerHTML = `
    <div class="page">
      <header class="head" id="mobileHead">
        <div class="pc-name"><i class="dot" id="connDot"></i>Pocket Composer<small id="connText">正在连接电脑</small></div>
        <button id="historyBtn" aria-label="最近图文">最近</button>
        <button id="settingsBtn" aria-label="设置">设置</button>
      </header>
      <section class="composer" id="composer">
        <div class="composer-heading">这次想做什么？</div>
        <div class="attach" id="attachments"></div>
        <div id="conflictBanner" class="conflict" hidden>
          <b>手机和电脑有不同的草稿</b><p>两份内容都还在，请选择这次继续使用哪一份。</p>
          <button id="useLocal">继续手机这份</button><button id="useServer">采用电脑这份</button>
        </div>
        <textarea id="text" placeholder="点这里，用手机输入法说话…&#10;&#10;也可以圈出问题，或画个草图。" aria-label="本次图文说明"></textarea>
        <div class="writehint"><span>用你习惯的输入法，不需要 API Key</span><span id="charCount">0 字</span></div>
        <div class="writehint"><span id="captionHint"></span></div>
        <div class="tools">
          <button id="captureBtn">截电脑</button>
          <button id="photoBtn">相册</button>
          <button id="boardBtn">白板</button>
        </div>
        <button class="primary" id="sendBtn" disabled>插入电脑</button>
        <p id="sync">图在前，文字在后 · 不自动发送</p><p id="localSave" role="status" aria-live="polite"></p>
      </section>
      <section class="editor" id="editor">
        <div class="head">
          <button id="back" aria-label="返回并保留编辑">←</button>
          <b id="editTitle">图片标注</b>
          <button id="undoBtn" aria-label="撤销">撤</button>
          <button id="redoBtn" aria-label="重做">重</button>
          <button class="primary" id="done">完成</button>
        </div>
        <div id="stage"></div>
        <div class="crop-actions" id="cropActions">
          <button id="cropReset">全图</button>
          <button id="cropApply">应用裁剪</button>
        </div>
        <div class="palette">
          <button data-color="#D45243" class="swatch selected" style="background:#D45243"></button>
          <button data-color="#326AC5" class="swatch" style="background:#326AC5"></button>
          <button data-color="#167D71" class="swatch" style="background:#167D71"></button>
          <button data-color="#1D2826" class="swatch" style="background:#1D2826"></button>
          <button id="widthBtn">中 · 5</button>
        </div>
        <div class="palette">
          <button data-tool="pen" class="selected">画笔</button>
          <button data-tool="arrow">箭头</button>
          <button data-tool="rect">方框</button>
          <button data-tool="number">编号</button>
          <button data-tool="crop">裁剪</button>
          <button id="moreBtn">更多</button>
        </div>
        <div class="palette extra" id="extra">
          <button data-tool="marker">记号笔</button>
          <button data-tool="highlight">荧光笔</button>
          <button data-tool="ellipse">椭圆</button>
          <button data-tool="line">直线</button>
          <button data-tool="text">文字</button>
          <button data-tool="eraser">橡皮</button>
          <button data-tool="mask">遮挡</button>
          <button data-tool="select">选择</button>
          <button id="wire">线框按钮</button>
        </div>
        <div class="caption-drawer" id="captionDrawer">
          <textarea id="captionInput" placeholder="给这张图补一句说明，不发Enter"></textarea>
        </div>
      </section>
    </div>
    <input id="file" type="file" accept="image/png,image/jpeg,image/webp" multiple hidden />
    <div class="sheet" id="sheet"><div class="card" id="sheetCard"></div></div>
  `;

  const state = {
    text: "",
    revision: 0,
    draft_id: "",
    epoch: "",
    assets: [] as Asset[],
    session: null as Session | null,
    online: false,
    uploading: false,
    editorKind: "图片标注",
    removed: [] as Asset[],
    conflict: null as any,
    sending: false,
  };
  let ws: WebSocket | null = null;
  let editor: SharedEditor | null = null;
  let currentId = "";
  const blobUrls: string[] = [];
  let reconnectTimer = 0;
  let closingForAuth = false;
  let sheetRevision = 0;
  let sessionReady = false;

  function rememberBlob(url: string): string {
    if (url.startsWith("blob:")) blobUrls.push(url);
    return url;
  }

  function forgetBlobs(): void {
    while (blobUrls.length) {
      URL.revokeObjectURL(blobUrls.pop()!);
    }
  }
  const $ = (id: string) => document.getElementById(id)!;
  const headers = (): Record<string, string> =>
    state.session
      ? { "X-DT-Session": state.session.session_id, "X-DT-Token": state.session.token }
      : {};

  function toast(t: string) {
    $("sync").textContent = t;
  }

  const DRAFT_KEY = "dt.v3.draft";
  let restored = false;
  let persistTimer = 0;
  const repository = new DraftRepository(status => {
    $("localSave").textContent = status === "saved" ? "草稿已保存在这台手机" :
      status === "saving" ? "正在保存手机草稿…" : "手机存储不可用；请先发送或保留此页面，勿直接关闭";
  });

  function draftSnapshot(): SavedDraft {
    return {schema: 1, text: state.text, revision: state.revision,
      draft_id: state.draft_id, epoch: state.epoch, saved_at: Date.now(),
      assets: state.assets.map(a => ({...a}))};
  }

  function persistDraft() {
    if (!restored) return;
    window.clearTimeout(persistTimer);
    persistTimer = window.setTimeout(() => repository.save(draftSnapshot()), 120);
  }

  async function restoreDraft() {
    let saved: any = null;
    try { saved = await repository.load(); }
    catch { $("localSave").textContent = "无法读取手机存储；已有内容不会被清除"; }
    if (!saved) {
      // 只迁移旧记录；成功保存之前不删除旧备份。
      try { saved = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || "null"); } catch {}
    }
    if (saved && typeof saved === "object") {
      state.text = String(saved.text || "");
      state.revision = Number(saved.revision || 0);
      state.draft_id = String(saved.draft_id || "");
      state.epoch = String(saved.epoch || "");
      state.assets = Array.isArray(saved.assets) ? saved.assets.slice(0,6) : [];
      for (const a of state.assets) {
        if (!a.id || typeof a.preview !== "string") {a.id ||= newId(); a.preview = ""; a.status = "failed";}
        if (a.status === "editing") a.status = "failed";
      }
    }
    restored = true;
  }

  function sendLabel(): string {
    if (!state.online || !state.session) return "未连接";
    if (state.uploading) return "图片上传中";
    if (state.sending) return "正在插入…";
    if (state.assets.some(a => !a.asset_id || a.status !== "ready")) return "请先完成图片";
    if (!state.text.trim() && !state.assets.length) return "插入电脑";
    return state.assets.length ? `插入 ${state.assets.length} 张图和文字` : "插入并复制";
  }

  let attachmentsSignature = "";
  function update() {
    const input = $("text") as HTMLTextAreaElement;
    if (input.value !== state.text) input.value = state.text;
    $("charCount").textContent = `${[...state.text].length} 字`;
    $("captionHint").textContent = state.assets.map((a, i) => `${i + 1}·${a.kind}`).join(" ");
    $("connText").textContent = state.online ? "已连接电脑" : "正在连接电脑";
    const btn = $("sendBtn") as HTMLButtonElement;
    btn.textContent = sendLabel();
    btn.disabled = !state.online || !state.session || state.uploading || state.sending || !!state.conflict ||
      state.assets.some(a => !a.asset_id || (a.status && a.status !== "ready")) || (!state.text.trim() && !state.assets.length);
    $("conflictBanner").hidden = !state.conflict;
    persistDraft();
    const signature = JSON.stringify(state.assets.map(a => [a.id,a.asset_id,a.status,a.render_revision,a.preview]));
    if (signature === attachmentsSignature) return;
    attachmentsSignature = signature;
    const strip = $("attachments");
    strip.replaceChildren();
    if (!state.assets.length) {
      strip.classList.add("empty");
      return;
    }
    strip.classList.remove("empty");
    state.assets.forEach((a, i) => {
      const wrap = document.createElement("div");
      wrap.className = "attach-card";
      const status = a.status === "queued" ? "排队" : a.status === "editing" ? "编辑中" : a.status === "failed" ? "未传完" : "就绪";
      wrap.innerHTML = `<img alt="${i + 1} · ${a.kind}" /><label>${i + 1} · ${a.kind} · ${status}</label><button class="left">←</button><button class="right">→</button><button class="remove">删</button>`;
      const img = wrap.querySelector("img") as HTMLImageElement;
      if (a.preview.startsWith("/v3/assets/") && state.session) {
        void fetch(a.preview, {headers: headers()}).then(async res => {
          if (!res.ok) return;
          const url = URL.createObjectURL(await res.blob());
          img.onload = img.onerror = () => URL.revokeObjectURL(url);
          img.src = url;
        }).catch(() => {});
      } else img.src = a.preview;
      img.addEventListener("click", () => {
        void openEditor(a.kind === "白板" ? "快速白板" : "图片标注", a).catch(editorFailure);
      });
      wrap.querySelector(".left")!.addEventListener("click", (ev) => {
        ev.stopPropagation();
        move(i, -1);
      });
      wrap.querySelector(".right")!.addEventListener("click", () => move(i, 1));
      wrap.querySelector(".remove")!.addEventListener("click", () => removeAt(i));
      strip.append(wrap);
    });
  }

  function move(i: number, dir: number) {
    const j = i + dir;
    if (j < 0 || j >= state.assets.length) return;
    const copy = state.assets.splice(i, 1)[0];
    state.assets.splice(j, 0, copy);
    sendDraft();
    update();
  }

  function removeAt(i: number) {
    state.removed.push(state.assets.splice(i, 1)[0]);
    sendDraft();
    update();
  }

  function connect() {
    if (!state.session) return;
    window.clearTimeout(reconnectTimer);
    if (ws && ws.readyState <= 1) return;
    closingForAuth = false;
    sessionReady = false;
    const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    ws = socket;
    ws.onopen = () => {
      state.online = false;
      update();
      ws!.send(JSON.stringify({ protocol: 3, type: "session.hello", session_id: state.session?.session_id, token: state.session?.token }));
    };
    ws.onclose = () => {
      if (ws !== socket) return;
      state.online = false;
      sessionReady = false;
      ws = null;
      update();
      if (!closingForAuth && state.session) reconnectTimer = window.setTimeout(connect, 1500);
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (looksLikeKeyScript(msg)) return;
      if (msg.type === "session.ready") {
        state.online = true;
        sessionReady = true;
        void pullRememberedSecret();
        const decision = applyReady(state, msg);
        if (decision === "conflict") {
          toast("电脑上已有另一份稿，当前未发出的稿还在，没有覆盖服务器");
          update();
          return;
        }
        if (decision === "adopt" && (state.text || state.assets.length)) sendDraft();
        update();
        void fetch("/v3/phone/event", {headers: headers()}).then(r => r.ok ? r.json() : null).then(event => {
          if (event?.type === "draft.rotated") {
            if (applyRotated(state, event) === "cleared") update();
          }
        }).catch(() => {});
      }
      if (msg.type === "device.remembered") {
        if (msg.device_id && msg.device_secret) storeDevice(String(msg.device_id), String(msg.device_secret));
        toast("已保存这台设备，下次可直接续接");
      }
      if (msg.type === "draft.ack") {
        toast(msg.error ? "草稿未同步，原文已保留" : msg.parked ? "电脑正在改字，手机稿已暂存" : msg.durable ? "电脑已收到 · 不自动发送" : "正在同步");
      }
      if (msg.type === "attempt.status") {
        state.sending = false;
        const labels: Record<string, string> = {CONFIRMED:"已放入输入框",UNKNOWN:"已尝试插入，可召回重试",NO_STEPS:"未插入，请先选中电脑输入框",PARTIAL:"只完成一部分，请查看恢复选项",BUSY:"正在处理上一份内容"};
        toast(labels[msg.result] || "插入未完成，内容保留");
        update();
      }
      if (msg.type === "draft.rotated") {
        const cleared = applyRotated(state, msg) === "cleared";
        if (cleared) ($("text") as HTMLTextAreaElement).value = "";
        toast(cleared ? "已开始下一段" : "电脑已收窗，当前未发出的稿还在");
        update();
      }
      if (msg.type === "recall.ready") toast(msg.text_unchanged ? "已召回上次待插入，当前草稿未改" : "召回异常");
      if (msg.type === "error") {
        state.sending = false;
        update();
        const err = String(msg.error || "");
        if (/session revoked|session expired/i.test(err)) {
          sessionStorage.removeItem("dt.v3.session");
          state.session = null;
          closingForAuth = true;
          ws?.close();
          ws = null;
          void resumeRemembered().then((ok) => {
            if (!ok) showPair();
          }).catch(() => {toast("电脑未连接，草稿仍在"); showPair();});
          return;
        }
        toast(err.includes("not granted") || err === "CAPTURE_DENIED" ? "这台手机还没有截图权限，文字仍可同步" : err);
        return;
      }
      if (msg.type === "capture.result") {
        if (msg.error) {
          toast(String(msg.message || msg.error).includes("CAPTURE") || String(msg.error).includes("not granted")
            ? "这台手机还没有截图权限，文字仍可同步"
            : String(msg.message || msg.error));
          return;
        }
        const a: Asset = {
          id: msg.asset.asset_id,
          asset_id: msg.asset.asset_id,
          kind: "截图",
          preview: `/v3/assets/${msg.asset.asset_id}`,
          w: msg.asset.width,
          h: msg.asset.height,
        };
        a.status = "queued";
        a.source = a.preview;
        state.assets.push(a);
        sendDraft();
        update();
        void openNextQueued();
      }
    };
  }

  function assetRefs(): string[] {
    const unfinished = state.assets.filter((a) => !a.asset_id || (a.status && a.status !== "ready"));
    if (unfinished.length) {
      throw new Error("incomplete assets");
    }
    return state.assets.map((a) => a.asset_id as string);
  }

  function documents() {
    return state.assets.map(a => ({id: a.id, asset_id: a.asset_id || "", status: a.status || "ready",
      render_revision: a.render_revision || 1, caption: a.caption || ""}));
  }

  function sendDraft() {
    const message = buildDraftUpdate(state);
    persistDraft();
    if (!ws || ws.readyState !== 1 || !sessionReady || state.conflict) return;
    ws.send(JSON.stringify(message));
  }

  let termTimer = 0;
  $("text").addEventListener("input", (e) => {
    state.text = (e.target as HTMLTextAreaElement).value;
    sendDraft();
    update();
    window.clearTimeout(termTimer);
    termTimer = window.setTimeout(() => {
      void refreshTerms();
    }, 400);
  });
  async function refreshTerms() {
    if (!state.session || !state.text.trim()) return;
    const res = await fetch("/v3/terms?q=" + encodeURIComponent(state.text), { headers: headers() });
    if (!res.ok) return;
    const data = await res.json();
    if (data.hints && data.hints.length) toast(String(data.hints[0].hint));
  }
  $("boardBtn").onclick = () => {
    const a: Asset = { id: "board-" + Date.now(), kind: "白板", preview: "", w: 1600, h: 1000, status: "queued" };
    state.assets.push(a);
    sendDraft();
    update();
    void openNextQueued();
  };
  $("photoBtn").onclick = () => $("file").click();
  $("captureBtn").onclick = () => {
    if (!state.session || !ws) return;
    ws.send(JSON.stringify({ protocol: 3, type: "capture.request", session_id: state.session.session_id, token: state.session.token, scope: "primary" }));
  };
  $("cropApply").onclick = () => {
    if (!editor?.applyCrop()) toast("请拖出至少64×64像素的选区");
  };
  $("cropReset").onclick = () => editor?.resetCrop();

  async function fileToDataUrl(file: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  $("file").addEventListener("change", async (e) => {
    const files = Array.from((e.target as HTMLInputElement).files || []);
    for (const f of files) {
      if (state.assets.length >= 6) break;
      const allowed = /^(image\/png|image\/jpeg|image\/jpg|image\/webp)$/i.test(f.type) || /\.(png|jpe?g|webp)$/i.test(f.name);
      if (!allowed) {
        toast("不支持的图片类型");
        continue;
      }
      const preview = await fileToDataUrl(f);
      const a: Asset = { id: "p-" + f.name + Date.now(), kind: "图片", preview, source: preview };
      const image = new Image();
      image.src = preview;
      try {
        await image.decode();
      } catch {
        toast("图片无法解码");
        continue;
      }
      a.w = image.naturalWidth || 1;
      a.h = image.naturalHeight || 1;
      a.status = "queued";
      a.source = preview;
      state.assets.push(a);
    }
    (e.target as HTMLInputElement).value = "";
    sendDraft();
    update();
    void openNextQueued();
  });

  function editorOpen(): boolean {
    return $("editor").classList.contains("show");
  }

  async function openNextQueued() {
    if (editorOpen()) return;
    const next = state.assets.find((a) => a.status === "queued");
    if (!next) return;
    try {
      await openEditor(next.kind === "白板" ? "快速白板" : "图片标注", next);
    } catch { editorFailure(); }
  }

  async function openEditor(title: string, asset: Asset) {
    currentId = asset.id;
    asset.status = "editing";
    asset.render_revision = (asset.render_revision || 1) + 1;
    sendDraft();
    state.editorKind = title;
    $("composer").style.display = "none";
    $("mobileHead").style.display = "none";
    $("editor").classList.add("show");
    $("editTitle").textContent = title;
    ($("captionInput") as HTMLTextAreaElement).value = asset.caption || "";
    const host = $("stage") as HTMLDivElement;
    editor?.destroy();
    host.replaceChildren();
    editor = new SharedEditor(host, asset.w || 1600, asset.h || 1000);
    if (asset.scene) {
      editor.importScene(asset.scene);
      if (asset.source || asset.preview) {
        let src = asset.source || asset.preview;
        if (src.startsWith("/v3/assets/") && state.session) {
          const res = await fetch(src, { headers: headers() });
          if (!res.ok) throw new Error("SOURCE_READ_FAILED");
          src = await fileToDataUrl(await res.blob());
          asset.source = src;
        }
        await editor.rebindSource(src);
      }
    } else if (title === "快速白板") {
      editor.addBlankBoard(asset.w || 1600, asset.h || 1000);
      host.dataset.ready = "1";
    } else if (asset.source || asset.preview) {
      let src = asset.source || asset.preview;
      if (src.startsWith("/v3/assets/") && state.session) {
        const res = await fetch(src, { headers: headers() });
        if (!res.ok) {
          toast("图片需要登录后才能看");
          asset.status = "failed";
          return;
        }
        src = await fileToDataUrl(await res.blob());
        asset.source = src;
      }
      await editor.loadImage(src, asset.w || 1600, asset.h || 1000);
    }
    requestAnimationFrame(() => editor?.resize());
    update();
    if (ws?.readyState === 1) ws.send(JSON.stringify({ protocol: 3, type: "editor.activity", kind: "edit" }));
  }

  document.querySelectorAll("[data-tool]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-tool]").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      if (editor) editor.tool = (btn as HTMLElement).dataset.tool as Tool;
      $("cropActions").classList.toggle("show", (btn as HTMLElement).dataset.tool === "crop");
    });
  });
  document.querySelectorAll("[data-color]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-color]").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      if (editor) editor.color = (btn as HTMLElement).dataset.color || "#D45243";
    });
  });
  $("widthBtn").onclick = () => {
    if (!editor) return;
    const vals = [2, 5, 10];
    const i = (vals.indexOf(editor.width) + 1) % 3;
    editor.width = vals[i];
    $("widthBtn").textContent = ["细 · 2", "中 · 5", "粗 · 10"][i];
  };
  $("moreBtn").onclick = () => $("extra").classList.toggle("show");
  $("wire").onclick = () => editor?.addWireframe();
  $("undoBtn").onclick = () => editor?.undo();
  $("redoBtn").onclick = () => editor?.redo();

  async function finishEditor() {
    if (!editor || state.uploading) return;
    if (state.editorKind === "快速白板" && editor.ops === 0) {
      toast("先画一点内容，再加入本次图文");
      return;
    }
    const blob = await editor.exportBlob();
    const preview = await fileToDataUrl(blob);
    const item = state.assets.find((a) => a.id === currentId);
    if (item) {
      item.caption = ($("captionInput") as HTMLTextAreaElement).value.trim();
      const sceneData = JSON.parse(editor.exportScene());
      if (sceneData.source) sceneData.source.url = item.source || "";
      item.scene = JSON.stringify(sceneData);
      item.preview = preview;
      item.asset_id = undefined;
      if (state.session) {
        state.uploading = true;
        update();
        try {
          const bmp = await createImageBitmap(blob);
          item.w = bmp.width;
          item.h = bmp.height;
          bmp.close();
          // scene已在导出前保留，不用临时blob地址覆写持久源。
          const meta = await uploadPng(blob, headers(), item.w || 1, item.h || 1, item.kind === "白板" ? "whiteboard" : "markup");
          item.asset_id = meta.asset_id;
        } catch {
          toast("图片未同步，不会沿用原图");
          item.asset_id = undefined;
          item.status = "failed";
          state.uploading = false;
          sendDraft();
          $("editor").classList.remove("show");
          $("composer").style.display = "flex";
          $("mobileHead").style.display = "flex";
          editor?.destroy();
          editor = null;
          update();
          void openNextQueued();
          return;
        }
        state.uploading = false;
        item.status = "ready";
      } else {
        item.status = "failed";
      }
    }
    $("editor").classList.remove("show");
    $("composer").style.display = "flex";
    $("mobileHead").style.display = "flex";
    editor?.destroy();
    editor = null;
    sendDraft();
    update();
    void openNextQueued();
  }

  function saveOpenEditor() {
    if (!editor || !editorOpen()) return;
    const item = state.assets.find(a => a.id === currentId);
    if (!item) return;
    try {
      const scene = JSON.parse(editor.exportScene());
      if (scene.source) scene.source.url = item.source || "";
      item.scene = JSON.stringify(scene);
      item.caption = ($("captionInput") as HTMLTextAreaElement).value;
      repository.save(draftSnapshot());
    } catch { $("localSave").textContent = "当前编辑尚未保存，请保留页面"; }
  }
  $("stage").addEventListener("pointerup", () => window.setTimeout(saveOpenEditor, 0));
  $("captionInput").addEventListener("input", saveOpenEditor);
  for (const id of ["undoBtn", "redoBtn", "wire", "cropApply", "cropReset"]) {
    $(id).addEventListener("click", () => window.setTimeout(saveOpenEditor, 0));
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && restored) {
      window.clearTimeout(persistTimer);
      saveOpenEditor(); repository.save(draftSnapshot());
    }
  });

  function editorFailure() {
    state.uploading = false;
    const item = state.assets.find(a => a.id === currentId);
    if (item) {
      try { if (editor) item.scene = editor.exportScene(); } catch {}
      item.status = "failed";
      sendDraft();
    }
    toast("图片尚未准备好，编辑保留；可重试或返回");
    update();
  }

  $("done").onclick = () => {
    void finishEditor().catch(editorFailure);
  };
  $("back").onclick = () => {
    if (state.editorKind === "快速白板" && editor && editor.ops === 0) {
      state.assets = state.assets.filter((a) => a.id !== currentId);
      $("editor").classList.remove("show");
      $("composer").style.display = "flex";
      $("mobileHead").style.display = "flex";
      editor?.destroy();
      editor = null;
      sendDraft();
      update();
      void openNextQueued();
      return;
    }
    void finishEditor().catch(editorFailure);
  };

  $("sendBtn").onclick = () => { void sendBundle().catch(() => {
    state.sending = false; update(); toast("连接中断，图文已保留，没有自动重试");
  }); };
  async function sendBundle() {
    if (!state.session || !ws || !state.online) {
      toast("未连接，草稿保留");
      return;
    }
    if (!state.text.trim() && !state.assets.length) return;
    let refs: string[];
    try {
      refs = assetRefs();
    } catch {
      toast("还有图片没传完，不会先发残缺文字");
      return;
    }
    sendDraft();
    const boundRevision = state.revision;
    const boundEpoch = state.epoch;
    state.sending = true;
    update();
    ws.send(
      JSON.stringify({
        protocol: 3,
        type: "bundle.commit",
        text: state.text,
        revision: state.revision,
        asset_refs: refs,
        draft_id: state.draft_id,
        epoch: state.epoch,
        captions: state.assets.map((a) => a.caption || ""),
        asset_status: state.assets.map((a) => a.status || "ready"),
        asset_documents: documents(),
      })
    );
    const nonceRes = await fetch("/v3/nonce", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state.session) });
    if (!nonceRes.ok) {
      state.sending = false;
      update();
      toast("请在电脑确认插入权限。拒绝后仍可同步文字。练习插入用电脑 Alt+I。");
      return;
    }
    const nonce = await nonceRes.json();
    if (state.revision !== boundRevision || state.epoch !== boundEpoch) {
      state.sending = false;
      update();
      toast("内容刚有更新，请再次点插入");
      return;
    }
    ws.send(
      JSON.stringify({
        protocol: 3,
        type: "insert.intent",
        session_id: state.session.session_id,
        token: state.session.token,
        nonce: nonce.nonce,
        intent_id: newId(),
        trigger: "phone",
        text: state.text,
        revision: state.revision,
        asset_refs: refs,
        draft_id: state.draft_id,
        epoch: state.epoch,
        captions: state.assets.map((a) => a.caption || ""),
        asset_status: state.assets.map((a) => a.status || "ready"),
        asset_documents: documents(),
      })
    );
  };

  function pairCodeFromUrl(): string {
    try {
      return new URL(location.href).searchParams.get("pair") || "";
    } catch {
      return "";
    }
  }

  const DEVICE_KEY = "dt.v3.device";

  function storeDevice(deviceId: string, secret: string) {
    try {
      localStorage.setItem(DEVICE_KEY, JSON.stringify({ device_id: deviceId, device_secret: secret }));
    } catch {
      /* private mode */
    }
  }

  async function pullRememberedSecret() {
    if (!state.session) return;
    try {
      const res = await fetch("/v3/device/secret", { headers: headers() });
      if (!res.ok) return;
      const body = await res.json();
      if (body.device_id && body.device_secret) storeDevice(String(body.device_id), String(body.device_secret));
    } catch {
      /* ignore */
    }
  }

  async function resumeRemembered(): Promise<boolean> {
    sessionStorage.removeItem("dt.v3.session");
    state.session = null;
    let stored: { device_id?: string; device_secret?: string } | null = null;
    try {
      stored = JSON.parse(localStorage.getItem(DEVICE_KEY) || "null");
    } catch {
      stored = null;
    }
    if (!stored?.device_id || !stored.device_secret) return false;
    const res = await fetch("/v3/pair", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: stored.device_id, device_secret: stored.device_secret }),
    });
    if (!res.ok) return false;
    state.session = await res.json();
    sessionStorage.setItem("dt.v3.session", JSON.stringify(state.session));
    connect();
    update();
    toast("已用记住的设备续接");
    return true;
  }

  async function submitPair(code: string): Promise<boolean> {
    const res = await fetch("/v3/pair", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (!res.ok) return false;
    state.session = await res.json();
    sessionStorage.setItem("dt.v3.session", JSON.stringify(state.session));
    const clean = new URL(location.href); clean.searchParams.delete("pair");
    history.replaceState(null, "", clean.pathname + clean.search + clean.hash);
    ++sheetRevision;
    $("sheet").classList.remove("show");
    connect();
    update();
    return true;
  }

  function showPair() {
    ++sheetRevision;
    const sheet = $("sheet");
    const preset = pairCodeFromUrl();
    $("sheetCard").innerHTML = `<h2>连接这台电脑</h2><p>扫电脑上的二维码即可配对。备用才手输 4 位短码。手机不能自授按键或截屏。练习插入用电脑 Alt+I。召回是 Alt+Shift+I，不是跳过纠错。</p><input id="pairCode" /><button class="primary" id="pairGo">配对</button>`;
    (document.getElementById("pairCode") as HTMLInputElement).value = preset;
    sheet.classList.add("show");
    $("pairGo").onclick = async () => {
      await submitPair((document.getElementById("pairCode") as HTMLInputElement).value);
    };
    if (preset) void submitPair(preset);
  }

  $("historyBtn").onclick = async () => {
    if (!state.session) {
      showPair();
      return;
    }
    const res = await fetch("/v3/history", { headers: headers() });
    const data = await res.json();
    $("sheetCard").innerHTML =
      "<h2>最近图文</h2><p>召回上次不会覆盖当前草稿。Alt+Shift+I 是召回，不是跳过纠错。</p>" +
      (data.items || []).map((i: { asset_count: number; text_chars: number }) => `<div>${i.asset_count} 图 · ${i.text_chars} 字</div>`).join("") +
      '<button class="primary" id="recallLast">召回上次（保留当前草稿）</button>';
    $("sheet").classList.add("show");
    $("recallLast").onclick = () => {
      if (!ws || ws.readyState !== 1) return;
      ws.send(JSON.stringify({ protocol: 3, type: "recall.last" }));
      $("sheet").classList.remove("show");
    };
  };
  $("settingsBtn").onclick = () => {
    const version = ++sheetRevision;
    $("sheetCard").innerHTML = `<h2>连接与设置</h2>
      <p id="settingsStatus">正在读取电脑状态…</p><p id="settingsGrant"></p>
      <p>密钥只存在电脑，不配 Key 也能输入、画图和投递。</p>
      <p>拒绝截图仍可同步文字。截图和插入权限由电脑端批准。</p>
      <p>Alt+I 插入并复制 · Alt+Shift+I 召回上次。</p>
      <p>AI 文字辅助仅在电脑主动调用，不负责手机听写。</p>`;
    $("sheet").classList.add("show");
    void fetch("/v3/status", {headers:headers()}).then(async res => {
      if (!res.ok) throw new Error("offline");
      const st = await res.json();
      if (sheetRevision !== version) return;
      $("settingsStatus").textContent = `协议 ${st.protocol} · 草稿 r${st.revision}`;
      $("settingsGrant").textContent = state.session ? "权限可在电脑的连接窗口调整" : "尚未配对";
    }).catch(() => {
      if (sheetRevision === version) $("settingsStatus").textContent = "电脑未连接，草稿仍保留";
    });
  };

  async function resolveConflict(useLocal: boolean) {
    const remote = state.conflict;
    if (!remote) return;
    // 明确操作前保全本机稿；不把跨epoch旧稿自动伪装成服务器新稿。
    try { repository.save(draftSnapshot()); await repository.backup(draftSnapshot()); } catch {
      toast("无法保存恢复副本，暂不替换草稿"); return;
    }
    state.draft_id = remote.draft_id;
    state.epoch = remote.epoch;
    state.revision = remote.revision || 0;
    state.conflict = null;
    if (useLocal) sendDraft();
    else {
      state.text = remote.text || "";
      state.assets = remote.assets || (remote.asset_refs || []).map((id: string) => ({id, asset_id:id, kind:"图片", preview:`/v3/assets/${id}`, status:"ready"}));
    }
    update();
  }
  $("useLocal").onclick = () => { void resolveConflict(true); };
  $("useServer").onclick = () => { void resolveConflict(false); };
  $("sheet").onclick = (e) => {
    if (e.target === $("sheet")) $("sheet").classList.remove("show");
  };
  document.addEventListener("keydown", (e) => {
    if (e.key === "z" && (e.ctrlKey || e.metaKey) && state.removed.length) {
      state.assets.push(state.removed.pop()!);
      sendDraft(); update();
    }
  });

  try {
    state.session = JSON.parse(sessionStorage.getItem("dt.v3.session") || "null");
  } catch {
    state.session = null;
  }
  ($("text") as HTMLTextAreaElement).disabled = true;
  void restoreDraft().then(async () => {
    ($("text") as HTMLTextAreaElement).disabled = false;
    update();
    if (state.session) connect();
    else if (!await resumeRemembered()) showPair();
  }).catch(() => {
    restored = true;
    ($("text") as HTMLTextAreaElement).disabled = false;
    toast("电脑未连接，草稿仍在"); showPair();
  });
}
