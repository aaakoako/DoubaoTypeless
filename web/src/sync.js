export function receiptMatches(state, archived) {
  if (!archived) return false;
  if (archived.draft_id && archived.draft_id !== state.draft_id) return false;
  if (archived.epoch && archived.epoch !== state.epoch) return false;
  if (typeof archived.revision === "number" && archived.revision !== state.revision) return false;
  if (String(archived.text || "") !== state.text) return false;
  const archivedRefs = new Set(archived.asset_refs || []);
  const extras = (state.assets || []).filter((a) => a.asset_id && !archivedRefs.has(a.asset_id));
  return extras.length === 0;
}

export function applyRotated(state, msg) {
  const archived = msg.archived || null;
  const result = String(msg.result || archived?.result || "");
  if (result && result !== "CONFIRMED" && !archived) return "kept";
  if (!receiptMatches(state, archived)) return "kept";
  state.text = "";
  state.assets = [];
  state.draft_id = String(msg.draft_id || state.draft_id);
  state.epoch = String(msg.epoch || state.epoch);
  if (typeof msg.revision === "number") state.revision = msg.revision;
  state.conflict = null;
  return "cleared";
}

export function applyReady(state, msg) {
  const serverId = String(msg.draft_id || "");
  const serverEpoch = String(msg.epoch || "");
  if (!state.draft_id || !state.epoch) {
    if (serverId) state.draft_id = serverId;
    if (serverEpoch) state.epoch = serverEpoch;
    if (typeof msg.revision === "number") state.revision = msg.revision;
    return "adopt";
  }
  const same = state.draft_id === serverId && state.epoch === serverEpoch;
  if (same) {
    if (typeof msg.revision === "number") state.revision = msg.revision;
    return "same";
  }
  if (state.text || (state.assets && state.assets.length)) {
    state.conflict = {
      draft_id: serverId,
      epoch: serverEpoch,
      revision: typeof msg.revision === "number" ? msg.revision : undefined,
      text: msg.text,
    };
    return "conflict";
  }
  if (serverId) state.draft_id = serverId;
  if (serverEpoch) state.epoch = serverEpoch;
  if (typeof msg.revision === "number") state.revision = msg.revision;
  return "adopt";
}
