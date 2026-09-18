/** Pocket Composer v3 client protocol. Served runtime is composer.html. */
export const PROTOCOL = 3;
export type MessageType =
  | "session.hello"
  | "session.ready"
  | "draft.update"
  | "draft.ack"
  | "editor.activity"
  | "bundle.commit"
  | "bundle.ready"
  | "insert.intent"
  | "attempt.status"
  | "capture.request"
  | "capture.result"
  | "ping"
  | "pong";

export function looksLikeKeyScript(payload: Record<string, unknown>): boolean {
  const keys = Object.keys(payload);
  if (keys.some((k) => ["keys", "x", "y", "vk", "scan_code"].includes(k))) return true;
  const blob = JSON.stringify(payload).toLowerCase();
  return ["ctrl+v", "sendinput", "keybd_event", "shell", "cmd.exe"].some((t) => blob.includes(t));
}
