import { SharedEditor, type Tool } from "./editor/canvas";
import { looksLikeKeyScript } from "./transport/protocol";
import { uploadPng } from "./transport/upload";

type Session = { session_id: string; token: string; device_id?: string };
type Asset = {
  id: string;
  kind: string;
  preview: string;
  asset_id?: string;
  w?: number;
  h?: number;
  scene?: string;
};

export function boot(root: HTMLElement): void {
  root.innerHTML = `
    <div class="page">
      <header class="head" id="mobileHead">
        <div class="pc-name"><i class="dot" id="connDot"></i>Pocket Composer<small id="connText">正在连接电脑</small></div>
        <button id="historyBtn" aria-label="最近图文">近</button>
        <button id="settingsBtn" aria-label="设置">设</button>
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
      </section>
    </div>
    <input id="file" type="file" accept="image/png,image/jpeg,image/webp" multiple hidden />
    <div class="sheet" id="sheet"><div class="card" id="sheetCard"></div></div>
  `;

  const state = {
    text: "",
    revision: 0,
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
      wrap.innerHTML = `<img alt="${i + 1} · ${a.kind}" /><label>${i + 1} · ${a.kind}</label><button class="left">←</button><button class="right">→</button><button class="remove">删</button>`;
      const img = wrap.querySelector("img") as HTMLImageElement;
      img.src = a.preview;
      img.addEventListener("click", () => openEditor(a.kind === "白板" ? "快速白板" : "图片标注", a));
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
      if (msg.type === "draft.ack") toast("电脑已收到 · 不自动发送");
      if (msg.type === "attempt.status") toast(`电脑：${msg.result} · 未发送Enter`);
      if (msg.type === "recall.ready") toast(msg.text_unchanged ? "已召回上次待插入，当前草稿未改" : "召回异常");
      if (msg.type === "capture.result") {
        if (msg.error) {
          toast(String(msg.error));
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
        state.assets.push(a);
        openEditor("图片标注", a);
        update();
      }
    };
  }

  function assetRefs(): string[] {
    return state.assets.map((a) => a.asset_id).filter((id): id is string => Boolean(id));
  }

  function sendDraft() {
    if (!ws || ws.readyState !== 1) return;
    ws.send(
      JSON.stringify({
        protocol: 3,
        type: "draft.update",
        text: state.text,
        revision: ++state.revision,
        asset_refs: assetRefs(),
      })
    );
  }

  $("text").addEventListener("input", (e) => {
    state.text = (e.target as HTMLTextAreaElement).value;
    sendDraft();
    update();
  });
  $("boardBtn").onclick = () => {
    const a: Asset = { id: "board-" + Date.now(), kind: "白板", preview: "", w: 1600, h: 1000 };
    state.assets.push(a);
    openEditor("快速白板", a);
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

  $("file").addEventListener("change", async (e) => {
    const files = Array.from((e.target as HTMLInputElement).files || []);
    for (const f of files) {
      if (state.assets.length >= 6) break;
      const allowed = /^(image\/png|image\/jpeg|image\/jpg|image\/webp)$/i.test(f.type) || /\.(png|jpe?g|webp)$/i.test(f.name);
      if (!allowed) {
        toast("不支持的图片类型");
        continue;
      }
      const preview = URL.createObjectURL(f);
      const a: Asset = { id: "p-" + f.name + Date.now(), kind: "图片", preview };
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
      state.assets.push(a);
      openEditor("图片标注", a);
    }
    (e.target as HTMLInputElement).value = "";
    update();
  });

  function openEditor(title: string, asset: Asset) {
    currentId = asset.id;
    state.editorKind = title;
    $("composer").style.display = "none";
    $("mobileHead").style.display = "none";
    $("editor").classList.add("show");
    $("editTitle").textContent = title;
    const host = $("stage") as HTMLDivElement;
    host.replaceChildren();
    editor = new SharedEditor(host, asset.w || 1600, asset.h || 1000);
    if (title === "快速白板" && asset.scene) {
      editor.importScene(asset.scene);
    } else if (title === "快速白板") {
      editor.addBlankBoard(asset.w || 1600, asset.h || 1000);
      host.dataset.ready = "1";
    } else if (asset.preview) editor.loadImage(asset.preview, asset.w || 1600, asset.h || 1000);
    requestAnimationFrame(() => editor?.resize());
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
      item.preview = preview;
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
          toast("图片未同步");
        }
        state.uploading = false;
      }
    }
    $("editor").classList.remove("show");
    $("composer").style.display = "flex";
    $("mobileHead").style.display = "flex";
    editor = null;
    sendDraft();
    update();
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
    sendDraft();
    ws.send(JSON.stringify({ protocol: 3, type: "bundle.commit", text: state.text, revision: state.revision, asset_refs: assetRefs() }));
    const nonce = await (await fetch("/v3/nonce", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state.session) })).json();
    ws.send(
      JSON.stringify({
        protocol: 3,
        type: "insert.intent",
        session_id: state.session.session_id,
        token: state.session.token,
        nonce: nonce.nonce,
        intent_id: crypto.randomUUID(),
        trigger: "phone",
        text: state.text,
        revision: state.revision,
        asset_refs: assetRefs(),
      })
    );
  };

  function showPair() {
    const sheet = $("sheet");
    $("sheetCard").innerHTML = `<h2>连接这台电脑</h2><p>三步上手：打开地址 → 输入配对码 → 电脑确认插入/截图权限。手机不能自授按键或截屏。</p><input id="pairCode" /><button class="primary" id="pairGo">配对</button>`;
    sheet.classList.add("show");
    $("pairGo").onclick = async () => {
      const res = await fetch("/v3/pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: (document.getElementById("pairCode") as HTMLInputElement).value,
        }),
      });
      if (!res.ok) return;
      state.session = await res.json();
      sessionStorage.setItem("dt.v3.session", JSON.stringify(state.session));
      sheet.classList.remove("show");
      connect();
      update();
    };
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
    $("sheetCard").innerHTML = "<h2>简单设置</h2><p>不配 Key 也能画图和投递。密钥只存在电脑。</p>";
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
  update();
  if (state.session) connect();
  else showPair();
}
