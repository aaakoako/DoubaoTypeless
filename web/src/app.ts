import { SharedEditor, type Tool } from "./editor/canvas";
import { applyReady, applyRotated } from "./sync.js";
import { looksLikeKeyScript, newId } from "./transport/protocol";
import { uploadPng } from "./transport/upload";

type Session = { session_id: string; token: string; device_id?: string };
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
        <textarea id="text" placeholder="点这里，用手机输入法说话…&#10;&#10;也可以圈出问题，或画个草图。" aria-label="本次图文说明"></textarea>
        <div class="writehint"><span>用你习惯的输入法，不需要 API Key</span><span id="charCount">0 字</span></div>
        <div class="writehint"><span id="captionHint"></span></div>
        <div class="tools">
          <button id="captureBtn">截电脑</button>
          <button id="photoBtn">相册</button>
          <button id="boardBtn">白板</button>
        </div>
        <button class="primary" id="sendBtn" disabled>插入电脑</button>
        <p id="sync">图在前，文字在后 · 不自动发送</p>
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
  };
  let ws: WebSocket | null = null;
  let editor: SharedEditor | null = null;
  let currentId = "";
  const $ = (id: string) => document.getElementById(id)!;
  const headers = (): Record<string, string> =>
    state.session
      ? { "X-DT-Session": state.session.session_id, "X-DT-Token": state.session.token }
      : {};

  function toast(t: string) {
    $("sync").textContent = t;
  }

  const DRAFT_KEY = "dt.v3.draft";

  function persistDraft() {
    try {
      sessionStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({
          text: state.text,
          revision: state.revision,
          draft_id: state.draft_id,
          epoch: state.epoch,
          assets: state.assets.map((a) => ({
            id: a.id,
            kind: a.kind,
            asset_id: a.asset_id,
            w: a.w,
            h: a.h,
            scene: a.scene,
            caption: a.caption,
            status: a.status,
            preview: a.asset_id ? `/v3/assets/${a.asset_id}` : (a.preview || "").startsWith("blob:") ? "" : a.preview,
            source: a.source && !a.source.startsWith("blob:") ? a.source : a.asset_id ? `/v3/assets/${a.asset_id}` : "",
          })),
        })
      );
    } catch {
      /* quota or private mode */
    }
  }

  function restoreDraft() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || "null");
      if (!saved || typeof saved !== "object") return;
      state.text = String(saved.text || "");
      state.revision = Number(saved.revision || 0);
      state.draft_id = String(saved.draft_id || "");
      state.epoch = String(saved.epoch || "");
      state.assets = Array.isArray(saved.assets) ? saved.assets : [];
    } catch {
      /* ignore broken snapshot */
    }
  }

  function sendLabel(): string {
    if (!state.online || !state.session) return "未连接";
    if (state.uploading) return "上传中";
    if (!state.text.trim() && !state.assets.length) return "插入电脑";
    return "插入电脑";
  }

  function update() {
    ($("text") as HTMLTextAreaElement).value = state.text;
    $("charCount").textContent = `${[...state.text].length} 字`;
    $("captionHint").textContent = state.assets.map((a, i) => `${i + 1}·${a.kind}`).join(" ");
    $("connText").textContent = state.online ? "已连接电脑" : "正在连接电脑";
    const btn = $("sendBtn") as HTMLButtonElement;
    btn.textContent = sendLabel();
    btn.disabled = !state.online || !state.session || state.uploading || (!state.text.trim() && !state.assets.length);
    persistDraft();
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
      img.src = a.preview;
      img.addEventListener("click", () => {
        void openEditor(a.kind === "白板" ? "快速白板" : "图片标注", a);
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
    ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    ws.onopen = () => {
      state.online = true;
      update();
      ws!.send(JSON.stringify({ protocol: 3, type: "session.hello", session_id: state.session?.session_id, token: state.session?.token }));
    };
    ws.onclose = () => {
      state.online = false;
      update();
      setTimeout(connect, 1500);
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (looksLikeKeyScript(msg)) return;
      if (msg.type === "session.ready") {
        void pullRememberedSecret();
        const decision = applyReady(state, msg);
        if (decision === "conflict") {
          toast("电脑上已有另一份稿，当前未发出的稿还在，没有覆盖服务器");
          update();
          return;
        }
        if (decision === "adopt" && (state.text || state.assets.length)) {
          sendDraft();
        }
      }
      if (msg.type === "device.remembered") {
        if (msg.device_id && msg.device_secret) storeDevice(String(msg.device_id), String(msg.device_secret));
        toast("已保存这台设备，下次可直接续接");
      }
      if (msg.type === "draft.ack") toast("电脑已收到 · 不自动发送");
      if (msg.type === "attempt.status") toast(`电脑：${msg.result} · 未发送Enter`);
      if (msg.type === "draft.rotated") {
        const cleared = applyRotated(state, msg) === "cleared";
        if (cleared) ($("text") as HTMLTextAreaElement).value = "";
        toast(cleared ? "已开始下一段" : "电脑已收窗，当前未发出的稿还在");
        update();
      }
      if (msg.type === "recall.ready") toast(msg.text_unchanged ? "已召回上次待插入，当前草稿未改" : "召回异常");
      if (msg.type === "error") {
        const err = String(msg.error || "");
        if (/session revoked|session expired/i.test(err)) {
          sessionStorage.removeItem("dt.v3.session");
          state.session = null;
          ws?.close();
          void resumeRemembered().then((ok) => {
            if (!ok) showPair();
          });
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

  function sendDraft() {
    if (!ws || ws.readyState !== 1) return;
    let refs: string[];
    try {
      refs = assetRefs();
    } catch {
      toast("还有图片没传完，不会先发残缺文字");
      return;
    }
    ws.send(
      JSON.stringify({
        protocol: 3,
        type: "draft.update",
        text: state.text,
        revision: ++state.revision,
        draft_id: state.draft_id,
        epoch: state.epoch,
        asset_refs: refs,
        captions: state.assets.map((a) => a.caption || ""),
        asset_status: state.assets.map((a) => a.status || "ready"),
      })
    );
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

  async function fileToDataUrl(file: File): Promise<string> {
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
    await openEditor(next.kind === "白板" ? "快速白板" : "图片标注", next);
  }

  async function openEditor(title: string, asset: Asset) {
    currentId = asset.id;
    asset.status = "editing";
    state.editorKind = title;
    $("composer").style.display = "none";
    $("mobileHead").style.display = "none";
    $("editor").classList.add("show");
    $("editTitle").textContent = title;
    ($("captionInput") as HTMLTextAreaElement).value = asset.caption || "";
    const host = $("stage") as HTMLDivElement;
    host.replaceChildren();
    editor = new SharedEditor(host, asset.w || 1600, asset.h || 1000);
    if (asset.scene) {
      editor.importScene(asset.scene);
      if (asset.source || asset.preview) {
        let src = asset.source || asset.preview;
        if (src.startsWith("/v3/assets/") && state.session) {
          const res = await fetch(src, { headers: headers() });
          if (res.ok) src = URL.createObjectURL(await res.blob());
        }
        editor.rebindSource(src);
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
        src = URL.createObjectURL(await res.blob());
      }
      editor.loadImage(src, asset.w || 1600, asset.h || 1000);
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
    if (!editor) return;
    if (state.editorKind === "快速白板" && editor.ops === 0) {
      toast("先画一点内容，再加入本次图文");
      return;
    }
    const blob = await editor.exportBlob();
    const preview = URL.createObjectURL(blob);
    const item = state.assets.find((a) => a.id === currentId);
    if (item) {
      item.caption = ($("captionInput") as HTMLTextAreaElement).value.trim();
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
          item.scene = editor.exportScene();
          const meta = await uploadPng(blob, headers(), item.w || 1, item.h || 1, item.kind === "白板" ? "whiteboard" : "markup");
          item.asset_id = meta.asset_id;
        } catch {
          toast("图片未同步，不会沿用原图");
          item.asset_id = undefined;
          item.status = "failed";
          state.uploading = false;
          $("editor").classList.remove("show");
          $("composer").style.display = "flex";
          $("mobileHead").style.display = "flex";
          editor = null;
          update();
          void openNextQueued();
          return;
        }
        state.uploading = false;
        item.status = "ready";
      } else {
        item.status = "ready";
      }
    }
    $("editor").classList.remove("show");
    $("composer").style.display = "flex";
    $("mobileHead").style.display = "flex";
    editor = null;
    sendDraft();
    update();
    void openNextQueued();
  }

  $("done").onclick = () => {
    void finishEditor();
  };
  $("back").onclick = () => {
    if (state.editorKind === "快速白板" && editor && editor.ops === 0) {
      state.assets = state.assets.filter((a) => a.id !== currentId);
      $("editor").classList.remove("show");
      $("composer").style.display = "flex";
      $("mobileHead").style.display = "flex";
      editor = null;
      update();
      return;
    }
    void finishEditor();
  };

  $("sendBtn").onclick = async () => {
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
      })
    );
    const nonceRes = await fetch("/v3/nonce", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state.session) });
    if (!nonceRes.ok) {
      toast("请在电脑确认插入权限。拒绝后仍可同步文字。练习插入用电脑 Alt+I。");
      return;
    }
    const nonce = await nonceRes.json();
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
    $("sheet").classList.remove("show");
    connect();
    update();
    return true;
  }

  function showPair() {
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
    $("sheetCard").innerHTML = `<h2>简单设置</h2>
      <p>密钥只存在电脑；不配 Key 也能画图和投递。拒绝截图仍可同步文字。Alt+Shift+I 是召回，不再是跳过纠错。</p>
      <p>插入 / 召回：Alt+I / Alt+Shift+I</p>
      <p>最近图文：20份 · 24小时</p>
      <p>AI 纠错：可选 · 电脑 BYOK</p>`;
    $("sheet").classList.add("show");
  };
  $("sheet").onclick = (e) => {
    if (e.target === $("sheet")) $("sheet").classList.remove("show");
  };
  document.addEventListener("keydown", (e) => {
    if (e.key === "z" && (e.ctrlKey || e.metaKey) && state.removed.length) {
      state.assets.push(state.removed.pop()!);
      update();
    }
  });

  try {
    state.session = JSON.parse(sessionStorage.getItem("dt.v3.session") || "null");
  } catch {
    state.session = null;
  }
  restoreDraft();
  update();
  if (state.session) connect();
  else {
    void resumeRemembered().then((ok) => {
      if (!ok) showPair();
    });
  }
}
