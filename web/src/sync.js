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
