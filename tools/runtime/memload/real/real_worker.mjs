// RT-6 実 loader 試験 (#125): PluginPool (src/runtime/memory_budget.ts) を hostbridge の実 loader に接続する Worker。
// 実 loader = host_vst2.wasm の LoadLibraryW / FreeLibrary (hb_bridge.mjs) で、lowbase 版 OTT (DLL 1 本 = 1 Memory, initial 24 MiB) を
// PluginPool 経由で pin / unpin / LRU 追い出しする。判定は run_real.mjs 側。
import { ModuleTable, HostBridge, EmscriptenGuest, HMODULE_BASE } from "./hb_bridge.mjs";
import { PluginPool, MemoryBudget, DEFAULT_PLUGIN_CAPACITY } from "./memory_budget.js";

globalThis.Buffer = { from: (s) => Uint8Array.from(s, (c) => c.charCodeAt(0)) };
const SR = 44100, HALF = 128, NPLUG = 150, PINS_CHURN = 170;
const sha256 = async (u8) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", u8))].map((b) => b.toString(16).padStart(2, "0")).join("");
const loadFactory = async (url) => new Function((await (await fetch(url)).text()) + "\n;return createModule;")();

// hostbridge の LoadLibraryW は handle を loaded.size+1 から作るため、解放後に既存 handle と衝突する
// (FreeLibrary が別 module の登録を消す)。ここでは単調増加の採番に置き換える。他は hb_bridge.mjs の LoadLibraryW と同一。
class PoolBridge extends HostBridge {
  constructor(table) { super(table); this.hseq = 0; }
  LoadLibraryW(pPath) {
    const path = this.readWStr(pPath);
    const desc = this.table.resolve(path);
    this.lastLoadMode = this.errorMode;
    if (!desc) { this.lastError = 126; return 0n; }
    let lm = this.loaded.get(desc.id);
    if (lm) { lm.refs++; return lm.handle; }
    const guest = desc.acquire();
    guest.mod.hbHostCall = (eff, op, idx, vlo, vhi, ptr, opt) => this.upcall(guest, eff, op, idx, vlo, vhi, ptr, opt);
    guest.init();
    lm = { desc, guest, refs: 1, handle: HMODULE_BASE + BigInt(++this.hseq) * 0x10000n, entrySlots: new Map() };
    this.loaded.set(desc.id, lm); this.byHandle.set(lm.handle, lm);
    return lm.handle;
  }
}

function fillIn(f) {
  for (let i = 0; i < HALF; i++) { f[i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); f[HALF + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
}

async function runCase(mode) {
  const cap = mode === "neg_cap" ? 130 : DEFAULT_PLUGIN_CAPACITY;
  const free = mode !== "neg_nofree";
  const ottF = await loadFactory("ott_hb.cjs");
  const descs = [];
  for (let k = 0; k < NPLUG; k++) {
    descs.push({ id: `xfer.ott.vst2#${k}`, name: "OTT", vendor: "Xfer Records", format: "vst2", arch: "x64", aliases: [`OTT${k}_x64.dll`],
      exports: { VSTPluginMain: "VSTPluginMain", main: "VSTPluginMain" }, guests: [],
      acquire() { const g = this.guests.pop(); if (!g) throw new Error("pool empty"); return g; }, release() {} });
  }
  const table = new ModuleTable(); descs.forEach((d) => table.register(d));
  const bridge = new PoolBridge(table);
  const host = new WebAssembly.Instance(new WebAssembly.Module(await (await fetch("host_vst2.wasm")).arrayBuffer()), bridge.imports());
  bridge.attachHost(host);
  const x = host.exports;
  const wstr = (s) => {
    const p = x.host_alloc(2 * (s.length + 1)); const d = new DataView(x.memory.buffer);
    for (let i = 0; i < s.length; i++) d.setUint16(p + 2 * i, s.charCodeAt(i), true);
    d.setUint16(p + 2 * s.length, 0, true); return p;
  };
  const inB = x.host_alloc(2 * HALF * 4), outB = x.host_alloc(2 * HALF * 4), inA = x.host_alloc(16), outA = x.host_alloc(16);
  { const d = new DataView(x.memory.buffer); d.setBigUint64(inA, BigInt(inB), true); d.setBigUint64(inA + 8, BigInt(inB + HALF * 4), true); d.setBigUint64(outA, BigInt(outB), true); d.setBigUint64(outA + 8, BigInt(outB + HALF * 4), true); }

  const budget = new MemoryBudget(cap);
  const R = { mode, cap, free, loads: 0, pins: 0, err: null, atLoad: null, evictions: 0, peakInUse: 0, peakSize: 0, hashMismatch: 0, handleMismatch: 0, refHash: null };
  const pool = new PluginPool(budget, async (id) => {
    const k = Number(id.slice(1)); const d = descs[k];
    R.loads++;
    const mod = await ottF();
    d.guests.push(new EmscriptenGuest(mod));
    const eff = x.host_load_plugin(wstr(`C:\\Program Files\\Common Files\\VST2\\${d.vendor}\\${d.aliases[0]}`), SR, HALF);
    if (!eff) throw new Error(`LoadLibrary failed: ${id}`);
    const handle = bridge.loaded.get(d.id).handle;
    for (let i = 0; i < 20; i++) x.host_set_param(eff, i, i === 19 ? 0 : 0.5);
    x.host_dispatch(eff, 12, 0, 1n, 0, 0);
    return { value: { eff, handle, k }, dispose: () => { if (free) bridge.FreeLibrary(handle); } };
  });

  // OTT は block 間で DSP 状態を持つ。bit 一致を見られるのは cold ロード直後の初回 block だけ (基準 = 最初の cold ロード)。
  // warm pin (追い出されず残っていた instance) は、出力ではなくパラメータの読み戻しで instance の取り違えを見る。
  const use = async (k, held) => {
    const before = R.loads;
    const h = await pool.pin(`p${k}`);
    R.pins++;
    const { eff, handle } = h.value;
    if (bridge.loaded.get(descs[k].id)?.handle !== handle) R.handleMismatch++;
    if (R.loads !== before) {
      R.coldLoads = (R.coldLoads ?? 0) + 1;
      fillIn(new Float32Array(x.memory.buffer, inB, 2 * HALF));
      x.host_process(eff, inA, outA, HALF);
      const hash = await sha256(new Uint8Array(x.memory.buffer.slice(outB, outB + 2 * HALF * 4)));
      if (R.refHash === null) R.refHash = hash; else if (hash !== R.refHash) R.hashMismatch++;
    } else if (x.host_get_param(eff, 0) !== Math.fround(0.5)) R.paramMismatch = (R.paramMismatch ?? 0) + 1;
    R.peakInUse = Math.max(R.peakInUse, budget.inUse); R.peakSize = Math.max(R.peakSize, pool.size);
    if (held) held.push(h); else h.unpin();
  };

  const t0 = performance.now();
  try {
    // 1) sweep: 150 種を 1 回ずつ (96 を超えた分は LRU で追い出される)
    for (let k = 0; k < NPLUG; k++) await use(k, null);
    // 2) churn: 偏った参照 (70% が先頭 40 種) を 170 回、同時 pin は最大 3
    let seed = 12345; const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed; };
    const held = [];
    for (let i = 0; i < PINS_CHURN; i++) {
      const k = rnd() % 100 < 70 ? rnd() % 40 : rnd() % NPLUG;
      await use(k, held);
      if (held.length > 3) held.shift().unpin();
    }
    for (const h of held) h.unpin();
    R.finalSize = pool.size; R.finalInUse = budget.inUse;
    R.bridgeLoaded = bridge.loaded.size; R.bridgeHandles = new Set([...bridge.loaded.values()].map((l) => l.handle)).size;
    R.evictions = pool.evictions;
    // 3) 全解放: 参照が残らないこと (Memory が GC 対象になる条件)
    for (let k = 0; k < NPLUG; k++) pool.unload(`p${k}`);
    R.afterUnloadSize = pool.size; R.afterUnloadInUse = budget.inUse; R.afterUnloadBridge = bridge.loaded.size;
  } catch (e) {
    R.atLoad = R.loads;
    R.err = { name: e?.name, message: String(e?.message ?? e).slice(0, 160) };
  }
  R.sec = (performance.now() - t0) / 1000;
  return R;
}

self.onmessage = async (ev) => {
  const { mode } = ev.data;
  let R;
  try { R = await runCase(mode); } catch (e) { R = { mode, err: { name: e?.name, message: String(e?.message ?? e).slice(0, 160) }, fatal: true }; }
  postMessage(R);
};
