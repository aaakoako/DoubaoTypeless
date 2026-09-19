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

export function newId(): string {
  const cryptoObj = globalThis.crypto;
  if (cryptoObj && typeof cryptoObj.randomUUID === "function") {
    return cryptoObj.randomUUID();
  }
  if (!cryptoObj || typeof cryptoObj.getRandomValues !== "function") {
    throw new Error("secure random unavailable");
  }
  const bytes = new Uint8Array(16);
  cryptoObj.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
