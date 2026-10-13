// P8 ベンチ本体 (node / Chrome Worker 共用)。env = { rd(name): Promise<Uint8Array>, createMain(): Promise<Module>, rss(), hwm(), loadavg(), now() }
export const hostIn = new Float32Array(256);
for (let i = 0; i < 128; i++) { hostIn[i] = 0.5 * Math.sin(i * 0.1); hostIn[128 + i] = 0.5 * Math.cos(i * 0.07); }
let E = null; let SFX = ''; let TARGET_MS = 150; const WARM_MS = 500; let REPS = 5;
const rd = async (f) => E.rd(f.replace(/(_\d+)?\.wasm$/, (m, n) => SFX + (n ?? '') + '.wasm'));
const cat = (parts) => { const n = parts.reduce((a, p) => a + p.length, 0); const o = new Uint8Array(n); let k = 0; for (const p of parts) { o.set(p, k); k += p.length; } return o; };
const performance = globalThis.performance;
const leb = (n) => { const o = []; do { let b = n & 0x7f; n >>>= 7; if (n) b |= 0x80; o.push(b); } while (n); return o; };
function uniq(bytes, i) { // 末尾に custom section を足してバイト列を一意化 (V8 の NativeModule キャッシュを避ける)
  const nm = new TextEncoder().encode('p8uid'); const payload = [...leb(nm.length), ...nm, i & 255, (i >> 8) & 255, 0, 0];
  return cat([bytes, Uint8Array.from([0, ...leb(payload.length), ...payload])]);
}

const fnv = (f32) => { let h = 0x811c9dc5; const u = new Uint32Array(f32.buffer, f32.byteOffset, f32.length); for (const x of u) { h ^= x; h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(16); };
export const p50 = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };
const stubImports = (mod) => { const o = {}; for (const i of WebAssembly.Module.imports(mod)) { (o[i.module] ??= {})[i.name] = i.kind === 'function' ? () => 0 : undefined; } return o; };

// ---- 構成ローダ: {run(blocks), out(): Float32Array(256), n, mems: [WebAssembly.Memory...]} ----
async function loadStatic(cfg, N, t) { // 静的 1 module (cfg = static_abs / static_based)
  const bytes = await rd(`${cfg}_${N}.wasm`); const t0 = performance.now(); const mod = await WebAssembly.compile(bytes); const t1 = performance.now();
  const inst = await WebAssembly.instantiate(mod, stubImports(mod)); const t2 = performance.now(); const e = inst.exports;
  e.init_all(); const mem = e.memory; new Float32Array(mem.buffer, e.host_in_ptr(), 256).set(hostIn);
  const run = (b) => { for (let i = 0; i < b; i++) e.chain_block(N); };
  t && Object.assign(t, { compile: t1 - t0, instantiate: t2 - t1 });
  return { run, out: () => new Float32Array(mem.buffer, e.plugin_out(N - 1), 256), mems: [mem] };
}
async function loadSep(cfg, N, t, { distinct = true, copy = true } = {}) { // 単体 standalone wasm を N 個 (別 module/instance/memory)
  const base = await rd(`${cfg}.wasm`); const insts = []; let shared = null; const tc = [];
  const t00 = performance.now();
  for (let i = 0; i < N; i++) {
    const t0 = performance.now(); let mod;
    if (distinct) mod = await WebAssembly.compile(uniq(base, i)); else mod = shared ??= await WebAssembly.compile(base);
    const t1 = performance.now(); const inst = await WebAssembly.instantiate(mod, stubImports(mod)); const t2 = performance.now();
    inst.exports.plg_init(); insts.push(inst.exports); tc.push([t1 - t0, t2 - t1]);
  }
  t && Object.assign(t, { compile: tc.reduce((a, x) => a + x[0], 0), instantiate: tc.reduce((a, x) => a + x[1], 0), total: performance.now() - t00 });
  const inV = insts.map((e) => new Float32Array(e.memory.buffer, e.plg_in(), 256)); const outV = insts.map((e) => new Float32Array(e.memory.buffer, e.plg_out(), 256));
  inV[0].set(hostIn);
  const run = copy ? (b) => { for (let k = 0; k < b; k++) { inV[0].set(hostIn); for (let i = 0; i < N; i++) { insts[i].plg_process(); if (i + 1 < N) inV[i + 1].set(outV[i]); } } }
    : (b) => { for (let k = 0; k < b; k++) for (let i = 0; i < N; i++) insts[i].plg_process(); };
  return { run, out: () => outV[N - 1], mems: insts.map((e) => e.memory) };
}
async function loadDyn(cfg, N, t, { jsdrive = false } = {}) { // MAIN_MODULE + SIDE_MODULE x N (dlopen)
  const createMain = E.createMain; const side = await rd(`${cfg}.wasm`);
  const t0 = performance.now(); const M = await createMain(); const t1 = performance.now();
  const tl = [];
  for (let i = 0; i < N; i++) {
    const p = `/p${i}.so`; M.FS.writeFile(p, uniq(side, i)); const n = M.lengthBytesUTF8(p) + 1; const ptr = M._malloc(n); M.stringToUTF8(p, ptr, n);
    const a = performance.now(); const r = M._load_plugin(ptr); tl.push(performance.now() - a); if (r !== i) throw new Error(`dlopen failed ${r} for ${p}`);
  }
  t && Object.assign(t, { main_instantiate: t1 - t0, dlopen_sum: tl.reduce((a, b) => a + b, 0), dlopen_first: tl[0], dlopen_rest_p50: tl.length > 1 ? p50(tl.slice(1)) : null });
  new Float32Array(M.HEAPF32.buffer, M._host_in_ptr(), 256).set(hostIn);
  const run = jsdrive ? (b) => { for (let k = 0; k < b; k++) for (let i = 0; i < N; i++) M._call_one(i); } : (b) => { for (let k = 0; k < b; k++) M._chain_block(N); };
  return { run, out: () => new Float32Array(M.HEAPF32.buffer, M._plugin_out(N - 1), 256), mems: [M.wasmMemory ?? { buffer: M.HEAPU8.buffer }] };
}
const CFGS = {
  static_abs: (N, t) => loadStatic('static_abs', N, t), static_based: (N, t) => loadStatic('static_based', N, t),
  sep_abs_hi: (N, t) => loadSep('sep_abs_hi', N, t), sep_abs_lo: (N, t) => loadSep('sep_abs_lo', N, t), sep_based: (N, t) => loadSep('sep_based', N, t),
  sep_based_nocopy: (N, t) => loadSep('sep_based', N, t, { copy: false }), sep_based_shared: (N, t) => loadSep('sep_based', N, t, { distinct: false }),
  dyn_def: (N, t) => loadDyn('side_def', N, t), dyn_hid: (N, t) => loadDyn('side_hid', N, t), dyn_hid_jsdrive: (N, t) => loadDyn('side_hid', N, t, { jsdrive: true }),
};

export async function one(env, mode, cfg, N, { sfx = '', reps = 5, targetMs = 150 } = {}) {
  E = env; SFX = sfx; REPS = reps; TARGET_MS = targetMs;
  const env_ = () => ({ ...E.info, loadavg: E.loadavg() });
  const t = {}; const r0 = E.rss(); const tt0 = performance.now(); const h = await CFGS[cfg](N, t); const tload = performance.now() - tt0;
  if (mode === 'steady') {
    h.run(300); const pa = performance.now(); h.run(300); const est = (performance.now() - pa) * 1000 / 300; const blocks = Math.max(50, Math.ceil(TARGET_MS * 1000 / est)); h.run(Math.ceil(WARM_MS * 1000 / est)); const per = [];
    for (let r = 0; r < REPS; r++) { const a = performance.now(); h.run(blocks); per.push((performance.now() - a) * 1000 / blocks); }
    return { mode, cfg: cfg + SFX, N, us_per_block: p50(per), us_min: Math.min(...per), us_max: Math.max(...per), us_per_plugin: p50(per) / N, sig: fnv(h.out()), reps, blocks, ...env_() };
  } else if (mode === 'startup') {
    const a = performance.now(); h.run(1); const first = performance.now() - a; const b = performance.now(); h.run(1); const second = performance.now() - b;
    return { mode, cfg: cfg + SFX, N, load_ms: tload, first_block_ms: first, second_block_ms: second, ...t, ...env_() };
  } else if (mode === 'memory') {
    h.run(1); const bytes = h.mems.reduce((a, m) => a + m.buffer.byteLength, 0);
    return { mode, cfg: cfg + SFX, N, wasm_memory_bytes: bytes, memories: h.mems.length, rss_delta_bytes: E.rss() - r0, hwm_bytes: E.hwm(), ...env_() };
  }
}
export const CONFIG_GRID = {
  steady: ['static_abs', 'static_based', 'sep_abs_lo', 'sep_based', 'sep_based_nocopy', 'dyn_def', 'dyn_hid', 'dyn_hid_jsdrive'],
  startup: ['static_based', 'sep_based', 'sep_based_shared', 'dyn_hid', 'dyn_def'],
  memory: ['static_based', 'sep_abs_hi', 'sep_abs_lo', 'sep_based', 'sep_based_shared', 'dyn_hid'],
};
