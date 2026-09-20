export type SyncAsset = { id?: string; asset_id?: string; status?: string; render_revision?: number; caption?: string; [key: string]: unknown };
export type SyncState = { text: string; assets: any[]; draft_id: string; epoch: string; revision: number; conflict?: any };
export function receiptMatches(state: SyncState, archived: any): boolean;
export function applyRotated(state: SyncState, msg: any): "cleared" | "kept";
export function applyReady(state: SyncState, msg: any): "same" | "adopt" | "conflict";

export function buildDraftUpdate(state: SyncState): Record<string, any>;
