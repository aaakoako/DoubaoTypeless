import { sha256Bytes } from "./protocol";

export type AssetMeta = {asset_id: string; sha256: string; bytes: number; width: number;
  height: number; mime?: string; role?: string};
export type UploadTicket = {upload_id: string; chunk_size: number; sha256: string; bytes: number};
export type UploadOptions = {signal?: AbortSignal; ticket?: UploadTicket;
  checkpoint?: (ticket: UploadTicket) => void | Promise<void>;
  progress?: (sent: number, total: number) => void};

/** 分块重传是幂等数据操作。任何插入/截图命令都不走此重试器。 */
async function request(url: string, init: RequestInit, signal?: AbortSignal): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    if (signal?.aborted) throw new DOMException("cancelled", "AbortError");
    const timeout = new AbortController();
    const abort = () => timeout.abort();
    signal?.addEventListener("abort", abort, {once: true});
    const timer = setTimeout(abort, 60000);
    try {
      const response = await fetch(url, {...init, signal: timeout.signal});
      if (response.ok) {
        // 计时覆盖响应体，弱网不能收到头后一直挂起；这些接口只返回小型JSON。
        const body=await response.arrayBuffer();
        if (body.byteLength>256*1024) throw Object.assign(new Error("UPLOAD_REPLY_TOO_LARGE"),{fatal:true});
        return new Response(body,{status:response.status,headers:response.headers});
      }
      if (response.status < 500 && ![408,429].includes(response.status))
        throw Object.assign(new Error(`UPLOAD_HTTP_${response.status}`), {fatal: true, status: response.status});
      throw new Error("UPLOAD_TEMPORARY");
    } catch (error) {
      if (signal?.aborted || (error as any)?.fatal || attempt >= 2) throw error;
    } finally {clearTimeout(timer); signal?.removeEventListener("abort", abort);}
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(() => {signal?.removeEventListener("abort", cancelled); resolve();}, 500 * 2**attempt);
      const cancelled = () => {clearTimeout(t); reject(new DOMException("cancelled", "AbortError"));};
      signal?.addEventListener("abort", cancelled, {once: true});
      if (signal?.aborted) cancelled();
    });
  }
}

export async function uploadPng(blob: Blob, headers: Record<string,string>, width: number,
  height: number, role = "photo", options: UploadOptions = {}): Promise<AssetMeta> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const digest = sha256Bytes(bytes); // HTTP局域网也可校验，不要求服务端明文可信。
  let ticket = options.ticket;
  if (ticket && (ticket.sha256 !== digest || ticket.bytes !== bytes.length ||
      !Number.isInteger(ticket.chunk_size) || ticket.chunk_size < 1024 || ticket.chunk_size > 2*1024*1024 ||
      !/^[\w-]+$/.test(ticket.upload_id))) ticket = undefined;
  let missing: number[] | null = null;
  if (ticket) {
    try {
      const res = await request(`/v3/assets/${encodeURIComponent(ticket.upload_id)}/missing`, {headers}, options.signal);
      missing = (await res.json()).missing;
    } catch (error) {
      if ([400,404,410].includes((error as any)?.status)) ticket = undefined;
      else throw error;
    }
  }
  if (!ticket) {
    const res = await request("/v3/assets/init", {method:"POST", headers:{...headers,"Content-Type":"application/json"},
      body:JSON.stringify({mime:"image/png",bytes:bytes.length,sha256:digest,width,height,role})}, options.signal);
    const init = await res.json();
    if (!Number.isInteger(init.chunk_size) || init.chunk_size < 1024 || init.chunk_size > 2*1024*1024 ||
        typeof init.upload_id !== "string" || !/^[\w-]+$/.test(init.upload_id)) throw new Error("INVALID_UPLOAD_TICKET");
    ticket = {upload_id:init.upload_id,chunk_size:init.chunk_size,sha256:digest,bytes:bytes.length};
    await options.checkpoint?.(ticket);
  }
  const totalChunks = Math.ceil(bytes.length/ticket.chunk_size);
  if (!Array.isArray(missing)) missing = Array.from({length:totalChunks},(_,i)=>i);
  if (missing.some(i=>!Number.isInteger(i)||i<0||i>=totalChunks)) throw new Error("INVALID_MISSING_CHUNKS");
  let sent = bytes.length - missing.reduce((n,i)=>n+Math.min(ticket!.chunk_size, bytes.length-i*ticket!.chunk_size),0);
  options.progress?.(sent, bytes.length);
  for (const i of missing) {
    const chunk = bytes.slice(i*ticket.chunk_size,(i+1)*ticket.chunk_size);
    await request(`/v3/assets/${encodeURIComponent(ticket.upload_id)}/chunks/${i}`,
      {method:"PUT",headers,body:chunk}, options.signal);
    sent += chunk.length; options.progress?.(sent, bytes.length);
  }
  const done = await request(`/v3/assets/${encodeURIComponent(ticket.upload_id)}/complete`, {method:"POST",headers}, options.signal);
  const meta: AssetMeta = await done.json();
  if (meta.sha256 !== digest || meta.bytes !== bytes.length || !meta.asset_id) throw new Error("UPLOAD_CHECKSUM_MISMATCH");
  return meta;
}
