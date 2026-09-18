import { hexSha256 } from "./protocol";

export type AssetMeta = {
  asset_id: string;
  sha256: string;
  bytes: number;
  width: number;
  height: number;
  mime?: string;
  role?: string;
};

export async function uploadPng(
  blob: Blob,
  headers: Record<string, string>,
  width: number,
  height: number,
  role = "photo"
): Promise<AssetMeta> {
  const buf = new Uint8Array(await blob.arrayBuffer());
  const digest = hexSha256(await crypto.subtle.digest("SHA-256", buf));
  const initRes = await fetch("/v3/assets/init", {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ mime: "image/png", bytes: buf.length, sha256: digest, width, height, role }),
  });
  if (!initRes.ok) throw new Error("upload init failed");
  const init = await initRes.json();
  const chunkSize = Number(init.chunk_size);
  const uploadId = String(init.upload_id);
  const expected = Math.ceil(buf.length / chunkSize);
  for (let i = 0; i < expected; i += 1) {
    const slice = buf.slice(i * chunkSize, (i + 1) * chunkSize);
    let ok = false;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const put = await fetch(`/v3/assets/${uploadId}/chunks/${i}`, { method: "PUT", headers, body: slice });
      if (put.ok) {
        ok = true;
        break;
      }
    }
    if (!ok) throw new Error(`chunk ${i} failed`);
  }
  const missingRes = await fetch(`/v3/assets/${uploadId}/missing`, { headers });
  const missing = ((await missingRes.json()).missing || []) as number[];
  for (const i of missing) {
    const slice = buf.slice(i * chunkSize, (i + 1) * chunkSize);
    const put = await fetch(`/v3/assets/${uploadId}/chunks/${i}`, { method: "PUT", headers, body: slice });
    if (!put.ok) throw new Error(`resume chunk ${i} failed`);
  }
  const done = await fetch(`/v3/assets/${uploadId}/complete`, { method: "POST", headers });
  if (!done.ok) throw new Error("upload complete failed");
  return done.json();
}
