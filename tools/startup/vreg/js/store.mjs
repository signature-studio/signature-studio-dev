// store.mjs — vreg 永続化バックエンド。インターフェース: load(profile) / save(profile, record) / delete(profile)
//   record = { schema:1, seedVersion, machineGuid, savedAt, hkcu: model }   (HKLM はセッション内のみ)
export class MemoryStore {
  constructor() { this.m = new Map(); }
  async load(p) { const v = this.m.get(p); return v === undefined ? undefined : structuredClone(v); }
  async save(p, rec) { this.m.set(p, structuredClone(rec)); }
  async delete(p) { this.m.delete(p); }
}

// node 用: JSON ファイル (別プロセス間の「リロード」確認用)
export class FileStore {
  constructor(dir) { this.dir = dir; }
  async _fs() { return (this.fs ??= await import('node:fs/promises')); }
  _path(p) { return `${this.dir}/${encodeURIComponent(p)}.json`; }
  async load(p) { const fs = await this._fs(); try { return JSON.parse(await fs.readFile(this._path(p), 'utf8')); } catch (e) { if (e.code === 'ENOENT') return undefined; throw e; } }
  async save(p, rec) {
    const fs = await this._fs(); await fs.mkdir(this.dir, { recursive: true });
    const f = this._path(p); const tmp = `${f}.${process.pid}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(rec)); await fs.rename(tmp, f);
  }
  async delete(p) { const fs = await this._fs(); await fs.rm(this._path(p), { force: true }); }
}

// ブラウザ (main / Worker): IndexedDB。1 DB / 1 objectStore、key = profile 名。
export class IdbStore {
  constructor({ indexedDB = globalThis.indexedDB, dbName = 'webstudio-vreg', storeName = 'profiles' } = {}) {
    if (!indexedDB) throw new Error('IdbStore: indexedDB が利用できません');
    this.idb = indexedDB; this.dbName = dbName; this.storeName = storeName; this.db = null;
  }
  _open() {
    return (this.db ??= new Promise((res, rej) => {
      const r = this.idb.open(this.dbName, 1);
      r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains(this.storeName)) r.result.createObjectStore(this.storeName); };
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    }));
  }
  async _run(mode, fn) {
    const db = await this._open();
    return new Promise((res, rej) => {
      const tx = db.transaction(this.storeName, mode);
      let out; const req = fn(tx.objectStore(this.storeName));
      req.onsuccess = () => { out = req.result; };
      tx.oncomplete = () => res(out);
      tx.onerror = () => rej(tx.error || req.error);
      tx.onabort = () => rej(tx.error || new Error('IDB transaction aborted'));
    });
  }
  load(p) { return this._run('readonly', (s) => s.get(p)); }
  save(p, rec) { return this._run('readwrite', (s) => s.put(rec, p)); }
  delete(p) { return this._run('readwrite', (s) => s.delete(p)); }
  async close() { if (this.db) (await this.db).close(); this.db = null; }
}
