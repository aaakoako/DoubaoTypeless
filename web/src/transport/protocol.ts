export function looksLikeKeyScript(payload: Record<string, unknown>): boolean {
  if ("keys" in payload || "vk" in payload || "scan_code" in payload) return true;
  if (typeof payload.x === "number" && typeof payload.y === "number") return true;
  const { text: _text, ...control } = payload;
  const blob = JSON.stringify(control).toLowerCase();
  return ["sendinput", "keybd_event", "shell", "cmd.exe"].some((token) => blob.includes(token));
}

export function hexSha256(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
