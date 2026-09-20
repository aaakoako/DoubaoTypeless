// 同一源稿的回执才允许轮换；传输确认不等于目标应用已收到。
export function receiptMatches(state, archived) {
  if (!archived || archived.draft_id !== state.draft_id || archived.epoch !== state.epoch || archived.revision !== state.revision) return false;
  if (String(archived.source_text ?? archived.text ?? "") !== state.text) return false;
  const items = state.assets || [];
  if (items.some(a => !a.asset_id || (a.status && a.status !== "ready"))) return false;
  const refs = archived.asset_refs || [];
  if (refs.length !== items.length || items.some((a, i) => a.asset_id !== refs[i])) return false;
  if (Array.isArray(archived.assets)) {
    if (archived.assets.length !== items.length) return false;
    return items.every((a, i) => {
      const b = archived.assets[i];
      return (a.id || a.asset_id) === b.id && a.asset_id === b.asset_id &&
        (a.render_revision || 1) === (b.render_revision || 1) &&
        (a.caption || "") === (b.caption || "") && (b.status || "ready") === "ready";
    });
  }
  // 旧回执不能确认带版本/图注的新版素材，宁可保留，也不误清。
  return items.every(a => !(a.caption || "") && (a.render_revision || 1) === 1);
}

export function applyRotated(state, msg) {
  if (msg.rotated === false || !receiptMatches(state, msg.archived)) return "kept";
  if (!msg.epoch || msg.epoch === state.epoch || msg.draft_id !== state.draft_id) return "kept";
  state.text = "";
  state.assets = [];
  state.epoch = String(msg.epoch);
  state.revision = Number(msg.revision);
  state.conflict = null;
  return "cleared";
}

function contentMatches(state, msg) {
  if (typeof msg.text === "string" && msg.text !== state.text) return false;
  const refs = msg.asset_refs;
  if (Array.isArray(refs)) {
    if (refs.length !== state.assets.length) return false;
    if (state.assets.some((a, i) => a.asset_id !== refs[i] || (a.status && a.status !== "ready"))) return false;
  }
  return true;
}

export function applyReady(state, msg) {
  const same = state.draft_id === msg.draft_id && state.epoch === msg.epoch;
  const hasLocal = !!(state.text || state.assets.length);
  const hasRemote = !!(msg.text || (msg.asset_refs || []).length);
  if ((!same && hasLocal && (state.draft_id || hasRemote)) || (same && !contentMatches(state, msg) && hasLocal)) {
    state.conflict = { ...msg };
    return "conflict";
  }
  if (!same || !hasLocal) {
    state.draft_id = String(msg.draft_id || state.draft_id);
    state.epoch = String(msg.epoch || state.epoch);
    if (!hasLocal && typeof msg.text === "string") state.text = msg.text;
    if (!hasLocal && Array.isArray(msg.assets)) state.assets = msg.assets;
    else if (!hasLocal && hasRemote && (msg.asset_refs || []).length) {
      state.assets = msg.asset_refs.map(id => ({id, asset_id:id, kind:"图片", preview:`/v3/assets/${id}`, status:"ready"}));
    }
    if (Number.isInteger(msg.revision)) state.revision = msg.revision;
    state.conflict = null;
    return "adopt";
  }
  if (Number.isInteger(msg.revision)) state.revision = Math.max(state.revision, msg.revision);
  state.conflict = null;
  return "same";
}

/** 每次本地修改先形成版本化消息，即使离线/图片未完成也要使旧回执过期。 */
export function buildDraftUpdate(state) {
  state.revision = (Number(state.revision) || 0) + 1;
  return {
    protocol: 3, type: "draft.update", text: state.text,
    revision: state.revision, draft_id: state.draft_id, epoch: state.epoch,
    asset_refs: (state.assets || []).filter(a => a.asset_id).map(a => a.asset_id),
    asset_documents: (state.assets || []).map(a => ({
      id: a.id || a.asset_id, asset_id: a.asset_id || "", status: a.status || "ready",
      render_revision: a.render_revision || 1, caption: a.caption || ""
    }))
  };
}


/** 手机生成身份与版本。重连不采纳电脑较旧的正文或 epoch。 */
export function buildPrimaryUpdate(state, updateId) {
  return {...buildDraftUpdate(state), authority: "phone", generation: state.generation || 0,
    update_id: updateId};
}

/** 同一份手机源稿才可开始下一段；新一段由手机创建，不由旧服务器回执命名。 */
export function rotatePrimary(state, msg, makeId) {
  if (!msg.phone_primary || !msg.rotated || msg.generation !== (state.generation || 0) || !receiptMatches(state, msg.archived)) return "kept";
  state.text = ""; state.assets = []; state.epoch = makeId();
  state.generation = (state.generation || 0) + 1; state.revision = 0;
  state.conflict = null;
  return "cleared";
}

/** 一个在途快照 + 一个合并后的最新快照。只重试数据，从不重试插入命令。 */
export class DraftOutbox {
  constructor({send, persist, onState = () => {}, timer = (fn, ms) => setTimeout(fn, ms),
               cancel = id => clearTimeout(id), retryMs = 1600, debounceMs = 0}) {
    Object.assign(this, {send, persist, onState, timer, cancel, retryMs, debounceMs});
    this.latest = null; this.flight = null; this.acked = null; this.online = false;
    this.timeout = null; this.preparing = false; this.closed = false; this.waiters = [];
    this.failure = null;
  }
  offer(message) {
    this.latest = structuredClone(message); this.failure = null;
    this.onState(this.online ? "syncing" : "offline");
    this.settle(); void this.pump();
  }
  connect() {
    this.online = true; this.flight = null; this.acked = null; this.failure = null;
    this.cancel(this.timeout); void this.pump();
  }
  disconnect() {
    this.online = false; this.flight = null; this.cancel(this.timeout);
    this.onState("offline");
  }
  async pump() {
    if (this.closed || !this.online || this.flight || this.preparing || !this.latest || this.failure) return;
    if (this.acked === this.latest.update_id) { this.onState("synced"); this.settle(); return; }
    this.preparing = true;
    try {
      if (this.debounceMs) await new Promise(resolve => this.timer(resolve, this.debounceMs));
      if (!this.online || this.closed) return;
      const savingId = this.latest.update_id;
      await this.persist();
      if (!this.online || this.closed || !this.latest) return;
      if (this.latest.update_id !== savingId) {
        this.preparing = false; void this.pump(); return;
      }
      this.flight = structuredClone(this.latest);
      this.transmit();
    } catch { this.onState("save_failed"); }
    finally { this.preparing = false; }
  }
  transmit() {
    if (!this.flight || !this.online || this.closed) return;
    this.cancel(this.timeout);
    try { this.send(this.flight); this.onState("syncing"); }
    catch { this.onState("offline"); }
    this.timeout = this.timer(() => {
      if (!this.online || this.closed) return;
      this.onState("retrying");
      this.transmit();
    }, this.retryMs);
  }
  acknowledge(ack) {
    const f = this.flight;
    if (!f || ack.update_id !== f.update_id || ack.draft_id !== f.draft_id ||
        ack.epoch !== f.epoch || ack.revision !== f.revision || ack.generation !== f.generation) return false;
    if (!ack.durable || ack.error || ack.parked) return false;
    this.cancel(this.timeout); this.acked = f.update_id; this.flight = null;
    this.settle(); void this.pump(); return true;
  }
  reject(ack) {
    if (ack.update_id !== this.flight?.update_id) return;
    this.cancel(this.timeout); this.flight = null; this.failure = ack.error || "SYNC_REJECTED";
    this.onState("conflict"); this.settle();
  }
  settle() {
    for (const w of [...this.waiters]) {
      if (this.failure || (this.latest && w.id !== this.latest.update_id)) {
        w.done(new Error(this.failure || "DRAFT_CHANGED"));
      } else if (w.id === this.acked) w.done(null);
    }
  }
  flush(id = this.latest?.update_id, ms = 6000) {
    if (!id) return Promise.reject(new Error("NO_DRAFT"));
    if (this.online && id === this.acked) return Promise.resolve();
    if (this.latest?.update_id !== id) return Promise.reject(new Error("DRAFT_CHANGED"));
    return new Promise((resolve, reject) => {
      const entry = {id, done: error => {
        this.cancel(timeout); this.waiters = this.waiters.filter(w => w !== entry);
        error ? reject(error) : resolve();
      }};
      const timeout = this.timer(() => entry.done(new Error("SYNC_TIMEOUT")), ms);
      this.waiters.push(entry); this.settle(); void this.pump();
    });
  }
  close() {
    this.closed = true; this.disconnect();
    for (const w of [...this.waiters]) w.done(new Error("CLOSED"));
  }
}
