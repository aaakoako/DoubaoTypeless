/** 手机工作稿：图片像素与场景存 IndexedDB，不把大图塞进 sessionStorage。
 * 每次写入同一事务；失败保留内存及上次成功记录，并由界面明确提示。
 * 凭据不在本模块中保存。浏览器清理/私密模式仍可能移除数据，不承诺永久保存。
 */
export type SavedDraft = {
  schema: 1; text: string; revision: number; draft_id: string; epoch: string;
  assets: Record<string, unknown>[];
  saved_at: number; generation?: number; last_intent?: {signature:string;id:string}|null;
};
export type SaveState = "saving" | "saved" | "unavailable";
const DATABASE = "doubao-typeless-v3-drafts";
const STORE = "drafts";

export class DraftRepository {
  private db: Promise<IDBDatabase> | null = null;
  private pending: SavedDraft | null = null;
  private running = false;
  private waiters: Array<{resolve: () => void; reject: (e: Error) => void}> = [];
  private error: Error | null = null;
  constructor(private onState: (state: SaveState) => void = () => {}) {}

  private open(): Promise<IDBDatabase> {
    if (this.db) return this.db;
    this.db = new Promise<IDBDatabase>((resolve, reject) => {
      if (!globalThis.indexedDB) { reject(new Error("LOCAL_STORAGE_UNAVAILABLE")); return; }
      const request = indexedDB.open(DATABASE, 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE);
      };
      request.onerror = () => reject(new Error("LOCAL_STORAGE_UNAVAILABLE"));
      request.onblocked = () => reject(new Error("LOCAL_STORAGE_BLOCKED"));
      request.onsuccess = () => {
        const db = request.result;
        db.onversionchange = () => { db.close(); this.db = null; };
        resolve(db);
      };
    }).catch(error => {this.db = null; throw error;});
    return this.db;
  }

  async load(key = "current"): Promise<SavedDraft | null> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const request = tx.objectStore(STORE).get(key);
      tx.oncomplete = () => {
        const value = request.result;
        resolve(value?.schema === 1 && typeof value.text === "string" && Array.isArray(value.assets) ? value : null);
      };
      tx.onabort = tx.onerror = () => reject(new Error("LOCAL_STORAGE_READ_FAILED"));
    });
  }

  private async write(key: string, value: SavedDraft): Promise<void> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      let tx: IDBTransaction;
      try { tx = db.transaction(STORE, "readwrite", {durability: "strict"}); }
      catch { tx = db.transaction(STORE, "readwrite"); }
      // 所有内容在一个事务中替换；只在 oncomplete 后显示已保存。
      tx.oncomplete = () => resolve();
      tx.onabort = tx.onerror = () => reject(new Error("LOCAL_STORAGE_WRITE_FAILED"));
      try { tx.objectStore(STORE).put(value, key); }
      catch { try {tx.abort();} catch {} reject(new Error("LOCAL_STORAGE_WRITE_FAILED")); }
    });
  }

  save(value: SavedDraft): void {
    this.pending = structuredClone(value); // 合并高频更新，但不把新稿写在旧事务之前。
    this.error = null;
    this.onState("saving");
    if (!this.running) void this.drain();
  }

  private async drain(): Promise<void> {
    this.running = true;
    while (this.pending) {
      const value = this.pending;
      this.pending = null;
      try { await this.write("current", value); this.error = null; }
      catch {
        this.error = new Error("LOCAL_STORAGE_WRITE_FAILED");
        this.onState("unavailable");
        // 不丢正在等待的新快照；下一次真实用户改动可再次尝试。
        if (!this.pending) break;
      }
    }
    this.running = false;
    if (!this.error) this.onState("saved");
    const waiting = this.waiters.splice(0);
    for (const item of waiting) this.error ? item.reject(this.error) : item.resolve();
  }

  flush(): Promise<void> {
    if (!this.running && !this.pending) return this.error ? Promise.reject(this.error) : Promise.resolve();
    return new Promise((resolve, reject) => this.waiters.push({resolve, reject}));
  }

  async backup(value: SavedDraft): Promise<void> {
    await this.flush();
    await this.write("before-replace", value);
  }

  async replaceWithBackup(before: SavedDraft, after: SavedDraft): Promise<void> {
    await this.flush();
    const db = await this.open();
    await new Promise<void>((resolve, reject) => {
      let tx: IDBTransaction;
      try {tx = db.transaction(STORE, "readwrite", {durability: "strict"});}
      catch {tx = db.transaction(STORE, "readwrite");}
      tx.oncomplete = () => resolve();
      tx.onabort = tx.onerror = () => reject(new Error("LOCAL_STORAGE_WRITE_FAILED"));
      try {
        // A preceding completion receipt may already have archived this draft.
        // Resetting an empty/stuck state must not erase that recovery copy.
        if (before.text || before.assets.length) tx.objectStore(STORE).put(before, "before-replace");
        tx.objectStore(STORE).put(after, "current");
      } catch {try {tx.abort();} catch {} reject(new Error("LOCAL_STORAGE_WRITE_FAILED"));}
    });
    this.onState("saved");
  }
}
