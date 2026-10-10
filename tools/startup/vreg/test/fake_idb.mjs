// fake_idb.mjs — IdbStore が使う最小限の IndexedDB サブセット (open/upgradeneeded/transaction/objectStore get·put·delete)。
// 実ブラウザ検証は e2e_chrome.mjs。ここは node 単体テスト用 (structuredClone でスナップショットを保持し「ページ再読込」を模擬)。
export class FakeIDBFactory {
  constructor() { this.dbs = new Map(); }
  open(name, version = 1) {
    const req = { onsuccess: null, onerror: null, onupgradeneeded: null, result: null, error: null };
    queueMicrotask(() => {
      let rec = this.dbs.get(name);
      const fresh = !rec;
      if (!rec) { rec = { version, stores: new Map() }; this.dbs.set(name, rec); }
      const db = {
        objectStoreNames: { contains: (n) => rec.stores.has(n) },
        createObjectStore: (n) => { rec.stores.set(n, new Map()); },
        transaction: (n, mode) => makeTx(rec, n, mode),
        close() {},
      };
      req.result = db;
      if (fresh) req.onupgradeneeded?.({ target: req });
      setTimeout(() => req.onsuccess?.({ target: req }), 0);
    });
    return req;
  }
}
function makeTx(rec, storeName, mode) {
  const store = rec.stores.get(storeName);
  if (!store) throw new Error('NotFoundError: ' + storeName);
  const tx = { oncomplete: null, onerror: null, onabort: null, error: null };
  let pending = 0, scheduled = false;
  const done = () => { if (!scheduled && pending === 0) { scheduled = true; setTimeout(() => tx.oncomplete?.({}), 0); } };
  const mk = (fn) => {
    pending++;
    const r = { result: undefined, error: null, onsuccess: null, onerror: null };
    setTimeout(() => { r.result = fn(); r.onsuccess?.({ target: r }); pending--; done(); }, 0);
    return r;
  };
  tx.objectStore = () => ({
    get: (k) => mk(() => { const v = store.get(k); return v === undefined ? undefined : structuredClone(v); }),
    put: (v, k) => { if (mode !== 'readwrite') throw new Error('ReadOnlyError'); return mk(() => { store.set(k, structuredClone(v)); return k; }); },
    delete: (k) => { if (mode !== 'readwrite') throw new Error('ReadOnlyError'); return mk(() => { store.delete(k); return undefined; }); },
  });
  return tx;
}
