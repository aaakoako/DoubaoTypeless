export function receiptMatches(
  state: { text: string; assets: { asset_id?: string }[]; draft_id: string; epoch: string; revision: number },
  archived: { draft_id?: string; epoch?: string; revision?: number; text?: string; asset_refs?: string[] } | null | undefined
): boolean;

export function applyRotated(
  state: {
    text: string;
    assets: { asset_id?: string }[];
    draft_id: string;
    epoch: string;
    revision: number;
    conflict?: unknown;
  },
  msg: { archived?: object | null; draft_id?: string; epoch?: string; revision?: number; result?: string }
): "cleared" | "kept";

export function applyReady(
  state: {
    text: string;
    assets: { asset_id?: string }[];
    draft_id: string;
    epoch: string;
    revision: number;
    conflict?: unknown;
  },
  msg: { draft_id?: string; epoch?: string; revision?: number; text?: string }
): "same" | "adopt" | "conflict";
