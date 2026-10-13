// RT-6 負荷試験ページ (Chrome 内)。`?case=<name>[&neg=leak|cap][&cap=N]` で 1 ケースだけ実行し window.__result に結果を置く。
// 判定は run_memload.mjs (node 側) が行う。ここでは実測値と例外名だけを返す。
import { MemoryBudget, PluginPool, MemoryBudgetExceeded, createBudgetedMemory } from "/gen/memory_budget.js";

// 1 Memory (initial 1 page / max 64MiB = lowbase 相当) を持ち put(addr,v)/get(addr) を export する最小 wasm
const WASM = new Uint8Array([
  0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
  0x01, 0x0b, 0x02, 0x60, 0x02, 0x7f, 0x7f, 0x00, 0x60, 0x01, 0x7f, 0x01, 0x7f,
  0x03, 0x03, 0x02, 0x00, 0x01,
  0x05, 0x05, 0x01, 0x01, 0x01, 0x80, 0x08,
  0x07, 0x16, 0x03, 0x06, 0x6d, 0x65, 0x6d, 0x6f, 0x72, 0x79, 0x02, 0x00, 0x03, 0x70, 0x75, 0x74, 0x00, 0x00, 0x03, 0x67, 0x65, 0x74, 0x00, 0x01,
  0x0a, 0x13, 0x02, 0x09, 0x00, 0x20, 0x00, 0x20, 0x01, 0x36, 0x02, 0x00, 0x0b, 0x07, 0x00, 0x20, 0x00, 0x28, 0x02, 0x00, 0x0b,
]);
const mod = new WebAssembly.Module(WASM);
const q = new URLSearchParams(location.search);
const name = q.get("case");
const neg = q.get("neg");
const errInfo = (e) => ({ name: e?.name, message: String(e?.message ?? e).slice(0, 120) });
const hash = (id) => { let h = 2166136261; for (const c of id) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return h | 0; };
const leak = [];

let loads = 0;
const loadPlugin = async (id) => {
  loads++;
  const inst = new WebAssembly.Instance(mod, {});
  inst.exports.put(0, hash(id));
  if (neg === "leak") leak.push(inst); // 追い出し後も参照を持ち続ける故障注入 (Memory が回収されない)
  return { value: inst.exports, dispose: () => {} };
};
const check = (ex, id) => ex.get(0) === hash(id);

// 破棄済み検出用ローダ: dispose されると value.disposed=true。delayOf() 回のマイクロタスクを待ってから返す
function trackedLoader(delayOf) {
  const created = [];
  const load = async (id) => {
    for (let i = delayOf(); i > 0; i--) await null;
    const value = { id, disposed: false };
    created.push(value);
    return { value, dispose: () => { value.disposed = true; } };
  };
  return { created, load };
}

// ネガコン (neg=legacy): 修正前の pin() = ロード完了の await の後で pins++ する版。エントリ登録 (pins=0) から pins++ までの間に
// 別 id のロードが追い出しに来ると、破棄済みのエントリを pin 済みとして返す。PluginPool の内部 (entries / loading / loadOne) を直接使う
class LegacyPinPool extends PluginPool {
  async pin(id) {
    let e = this.entries.get(id);
    if (!e) {
      let l = this.loading.get(id);
      if (!l) {
        l = { waiters: 0 };
        l.promise = this.loadOne(id, () => 0).finally(() => this.loading.delete(id));
        this.loading.set(id, l);
      }
      e = await l.promise;
    }
    e.pins++;
    e.lastUsed = ++this.tick;
    let done = false;
    return { id, value: e.value, unpin: () => { if (done) return; done = true; e.pins--; } };
  }
}

function rng(seed) { let s = seed >>> 0; return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296); }

const cases = {
  // ネガコン: 予算なし・全保持。wasm32 で 1 レンダラ上限に達し RangeError になること (問題の再現)
  async naive() {
    const keep = []; let err = null;
    try { for (let i = 0; i < 300; i++) keep.push(new WebAssembly.Instance(mod, {})); } catch (e) { err = errInfo(e); }
    return { created: keep.length, err };
  },

  // 参照を落とした Memory は回収される (明示 GC なし)。保持なしで 1000 個作成 → 上限まで保持 → 全解放後に再び上限まで保持できること。
  // neg=keep: churn 中も参照を保持 → 上限で OOM (FAIL すること)
  async churn_drop() {
    const churn = { ok: 0, err: null }, keepChurn = [];
    try {
      for (let i = 0; i < 1000; i++) {
        const inst = new WebAssembly.Instance(mod, {});
        inst.exports.put(0, hash(`c${i}`));
        if (neg === "keep") keepChurn.push(inst);
        churn.ok++;
      }
    } catch (e) { churn.err = errInfo(e); }
    const fill = () => {
      const keep = []; let err = null;
      try { for (let i = 0; i < 300; i++) keep.push(new WebAssembly.Instance(mod, {})); } catch (e) { err = errInfo(e); }
      return { created: keep.length, err };
    };
    const first = fill();
    const second = fill();
    return { churn, first, second };
  },

  // wasm64 ロード中の追い出しで victim の dispose が throw しても、確保済みの枠を残さないこと (loadOne の巻き戻し)
  async dispose_throw() {
    const budget = new MemoryBudget(2);
    const pool = new PluginPool(budget, async (id) => {
      if (id === "w") return { value: { id }, kind: "wasm64", dispose: () => {} };
      return { value: { id }, dispose: () => { throw new Error("dispose-boom"); } };
    });
    (await pool.pin("a")).unpin();
    let err = null;
    try { await pool.pin("w"); } catch (e) { err = errInfo(e); }
    const afterFail = { inUse: budget.inUse, size: pool.size, hasW: pool.has("w") };
    let recovered = null;
    try { recovered = (await pool.pin("b")).id; } catch (e) { recovered = errInfo(e); }
    return { err, afterFail, recovered };
  },

  // 300 種のプラグインを cap=96 の予算で 1500 回 pin/unpin (Zipf 風 80/20 アクセス)。ネイティブ上限 124 を超えて累計ロードできること
  async pool_churn() {
    const cap = +(q.get("cap") ?? 96);
    const budget = new MemoryBudget(cap);
    const pool = new PluginPool(budget, loadPlugin);
    const ids = Array.from({ length: 300 }, (_, i) => `plg${i}`);
    const r = rng(12345);
    let peakInUse = 0, peakSize = 0, badState = 0, ok = 0, err = null;
    try {
      for (let i = 0; i < 1500; i++) {
        const id = r() < 0.8 ? ids[Math.floor(r() * 60)] : ids[Math.floor(r() * 300)];
        const h = await pool.pin(id);
        if (!check(h.value, id)) badState++;
        peakInUse = Math.max(peakInUse, budget.inUse); peakSize = Math.max(peakSize, pool.size);
        h.unpin(); ok++;
      }
    } catch (e) { err = errInfo(e); }
    return { cap, pins: ok, loads, evictions: pool.evictions, peakInUse, peakSize, badState, finalInUse: budget.inUse, err };
  },

  // 100+ 同時ロード: cap=120 (既定 ≤ネイティブ 124) で 120 本を Promise.all で同時 pin → 121 本目は MemoryBudgetExceeded (RangeError ではない)
  async pool_concurrent() {
    const cap = +(q.get("cap") ?? 120);
    const budget = new MemoryBudget(cap);
    const pool = new PluginPool(budget, loadPlugin);
    const ids = Array.from({ length: 120 }, (_, i) => `c${i}`);
    const t0 = performance.now();
    let handles = [], err = null;
    try { handles = await Promise.all(ids.map((id) => pool.pin(id))); } catch (e) { err = errInfo(e); }
    const ms = +(performance.now() - t0).toFixed(1);
    const stateOk = handles.every((h, i) => check(h.value, ids[i]));
    const sizeAfter = pool.size, inUseAfter = budget.inUse;
    let over = null;
    try { await pool.pin("overflow"); over = "no-error"; } catch (e) { over = errInfo(e); }
    const afterOverInUse = budget.inUse;
    // 1 本 unpin すれば 121 本目は LRU 追い出しで入る
    handles[0].unpin();
    let recovered = false;
    try { const h = await pool.pin("overflow"); recovered = check(h.value, "overflow"); } catch (e) { recovered = errInfo(e); }
    // 同一 id の同時 pin は 1 回しかロードしない
    const before = loads;
    const pool2 = new PluginPool(new MemoryBudget(8), loadPlugin);
    await Promise.all(Array.from({ length: 10 }, () => pool2.pin("same")));
    const dedupLoads = loads - before;
    return { cap, pinned: handles.length, ms, stateOk, sizeAfter, inUseAfter, over, afterOverInUse, recovered, evictions: pool.evictions, dedupLoads, err };
  },

  // pin の競合 (review 指摘): ロード完了 (エントリ登録) から pin が復帰するまでの間に、別 id のロードが枠不足で追い出しに来ても、
  // 破棄済み (dispose 済み・枠返却済み) のプラグインを pin 済みハンドルとして返さないこと。
  // (window) cap=1 で pin(A) の k マイクロタスク後に pin(B)。A は pin 済みなので追い出されず、B は MemoryBudgetExceeded になるのが正。
  // (stress) cap=8・24 種・並行 24 本を 60 波。ロード時間と保持時間はマイクロタスク数でばらつかせる
  async pool_race() {
    const Pool = neg === "legacy" ? LegacyPinPool : PluginPool;
    const window = [];
    for (let k = 0; k <= 8; k++) {
      const t = trackedLoader(() => 0);
      const budget = new MemoryBudget(1);
      const pool = new Pool(budget, t.load);
      const pa = pool.pin("A");
      for (let i = 0; i < k; i++) await null;
      const pb = pool.pin("B");
      const [ra, rb] = await Promise.allSettled([pa, pb]);
      window.push({
        k, aOk: ra.status === "fulfilled", aDisposed: ra.status === "fulfilled" ? ra.value.value.disposed : null, hasA: pool.has("A"),
        bOk: rb.status === "fulfilled", bErr: rb.status === "rejected" ? rb.reason?.name : null, inUse: budget.inUse, size: pool.size,
      });
    }

    const cap = 8, ids = Array.from({ length: 24 }, (_, i) => `r${i}`);
    const r = rng(777);
    const t = trackedLoader(() => Math.floor(r() * 4));
    const budget = new MemoryBudget(cap);
    const pool = new Pool(budget, t.load);
    let handed = 0, stale = 0, exceeded = 0, otherErr = null, peakInUse = 0;
    const task = async () => {
      for (let i = Math.floor(r() * 6); i > 0; i--) await null;
      const id = ids[Math.floor(r() * ids.length)];
      let h;
      try { h = await pool.pin(id); } catch (e) { if (e?.name === "MemoryBudgetExceeded") exceeded++; else otherErr ??= errInfo(e); return; }
      handed++;
      if (h.value.disposed || h.value.id !== id) stale++;
      for (let i = Math.floor(r() * 8); i > 0; i--) await null;
      if (h.value.disposed || !pool.has(id)) stale++;
      peakInUse = Math.max(peakInUse, budget.inUse);
      h.unpin();
    };
    for (let wave = 0; wave < 60; wave++) await Promise.all(Array.from({ length: 24 }, task));
    const liveOf = () => t.created.filter((v) => !v.disposed).length;
    const quiescent = { live: liveOf(), size: pool.size, inUse: budget.inUse };
    let drained = 0;
    while (pool.evictOne()) drained++;
    const afterDrain = { live: liveOf(), size: pool.size, inUse: budget.inUse };
    return { window, stress: { cap, tasks: 60 * 24, handed, exceeded, stale, otherErr, loads: t.created.length, evictions: pool.evictions, peakInUse, quiescent, drained, afterDrain } };
  },

  // Memory 生成の失敗時に枠が戻ること (budget が leak しない)
  async create_fail_releases() {
    const budget = new MemoryBudget(10);
    let err = null;
    try { createBudgetedMemory(budget, "bad", { initial: 2, maximum: 1 }); } catch (e) { err = errInfo(e); }
    const ok = createBudgetedMemory(budget, "good", { initial: 1, maximum: 16 });
    const inUseWithOk = budget.inUse;
    ok.lease.release(); ok.lease.release(); // 冪等
    return { err, inUseWithOk, inUseAfter: budget.inUse };
  },

  // main 60 + Worker: 共有カウンタ cap=120 → Worker は 60 本で止まり、実 Memory 合計 120、RangeError なし。budget=0 なら Worker は RangeError
  async cross_thread() {
    const useBudget = q.get("budget") !== "0";
    const cap = 120;
    const counter = MemoryBudget.createSharedCounter();
    const budget = new MemoryBudget(cap, counter);
    const keep = [];
    for (let i = 0; i < 60; i++) keep.push(createBudgetedMemory(budget, `main${i}`, { initial: 1, maximum: 65536 }));
    const w = new Worker("/worker.js", { type: "module" });
    const res = await new Promise((resolve, reject) => { w.onmessage = (e) => resolve(e.data); w.onerror = (e) => reject(new Error("worker error " + e.message)); w.postMessage({ counter, cap, useBudget }); });
    return { useBudget, mainCreated: keep.length, worker: res, inUse: budget.inUse };
  },

  // wasm64 (max 16GiB) は 1 Memory = 2 slot。cap=120 で 60 本まで予約でき、実 Memory も 60 本作れる (61 本目以降は予算が拒否)。
  // 実上限は 61〜62 本 (REPORT, 揺れる) なので cap は 120 (60 本) に置く
  async wasm64() {
    const budget = new MemoryBudget(+(q.get("cap") ?? 120));
    const keep = []; let denied = 0, err = null;
    try {
      for (let i = 0; i < 70; i++) {
        const l = budget.tryAcquire(`w64_${i}`, "wasm64");
        if (!l) { denied++; continue; }
        keep.push({ l, m: new WebAssembly.Memory({ address: "i64", initial: 1n, maximum: 262144n }) });
      }
    } catch (e) { err = errInfo(e); }
    return { granted: keep.length, denied, inUse: budget.inUse, err };
  },
};

try {
  const t0 = performance.now();
  const r = await cases[name]();
  window.__result = { case: name, neg: neg ?? null, ms: +(performance.now() - t0).toFixed(1), chrome: navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0], ...r };
} catch (e) {
  window.__result = { case: name, neg: neg ?? null, fatal: errInfo(e) };
}
// MemoryBudgetExceeded は export 済みだが、判定は name 文字列で行うため参照を残す
void MemoryBudgetExceeded;
