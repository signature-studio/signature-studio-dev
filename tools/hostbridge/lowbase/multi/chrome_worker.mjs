// chrome_worker.mjs — headless Chrome の dedicated Worker 内で multi_load と同等の試験を行う (lowbase module を Web 環境でロード).
//   OTT×NMOD (+ Balance kernel) を同一 host/bridge に載せ、500blk×128f の出力 sha256 を返す。さらに NSPAWN 個の OTT instance を追加生成して Memory 個数/時間を測る。
import { ModuleTable, HostBridge, EmscriptenGuest } from './hb_bridge.mjs';
globalThis.Buffer = { from: (s) => Uint8Array.from(s, (c) => c.charCodeAt(0)) }; // bridge の Buffer.from(latin1) 用 (browser polyfill)
const loadFactory = async (url) => new Function((await (await fetch(url)).text()) + '\n;return createModule;')();
const sha256 = async (u8) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', u8))].map((b) => b.toString(16).padStart(2, '0')).join('');
self.onmessage = async (ev) => {
  const { nmod, nspawn, nblk } = ev.data; const R = { nmod, errors: [] };
  try {
    const ottF = await loadFactory('ott_hb.cjs'), balF = await loadFactory('bal_hb.cjs');
    const mk = (id, alias, name, vendor, mod) => { const pool = [new EmscriptenGuest(mod)]; return { id, name, vendor, format: 'vst2', arch: 'x64', aliases: [alias], exports: { VSTPluginMain: 'VSTPluginMain', main: 'VSTPluginMain' }, acquire() { return pool.pop(); }, release() {} }; };
    const descs = [];
    for (let k = 0; k < nmod; k++) descs.push(mk(`xfer.ott.vst2#${k}`, `OTT${k}_x64.dll`, 'OTT', 'Xfer Records', await ottF()));
    descs.push(mk('imageline.balance.kernel', 'BalanceK_x64.dll', 'Balance', 'Image-Line', await balF()));
    R.ott_linear_bytes = descs[0].acquire === undefined ? 0 : null;
    const table = new ModuleTable(); descs.forEach((d) => table.register(d));
    const bridge = new HostBridge(table);
    const hostBytes = await (await fetch('host_vst2.wasm')).arrayBuffer();
    const inst = new WebAssembly.Instance(new WebAssembly.Module(hostBytes), bridge.imports()); bridge.attachHost(inst); const x = inst.exports;
    const dv = () => new DataView(x.memory.buffer);
    const wstr = (s) => { const p = x.host_alloc(2 * (s.length + 1)); const d = dv(); for (let i = 0; i < s.length; i++) d.setUint16(p + 2 * i, s.charCodeAt(i), true); d.setUint16(p + 2 * s.length, 0, true); return p; };
    const effs = descs.map((d) => x.host_load_plugin(wstr(`C:\\Program Files\\Common Files\\VST2\\${d.vendor}\\${d.aliases[0]}`), 44100, 128));
    R.loaded_ok = effs.every((e) => e !== 0);
    R.linear_mib = [...bridge.loaded.values()].map((lm) => lm.guest.mod.HEAPU8.length / 1048576);
    for (let k = 0; k < nmod; k++) { for (let i = 0; i < 20; i++) x.host_set_param(effs[k], i, i === 19 ? 0 : 0.5); x.host_dispatch(effs[k], 12, 0, 1n, 0, 0); }
    [0.8, 0.5, 0.3, -0.2, 0, 0, 0, 0].forEach((v, i) => x.host_set_param(effs[nmod], i, v)); x.host_dispatch(effs[nmod], 12, 0, 1n, 0, 0);
    const H = 128, mkAudio = () => { const inB = x.host_alloc(2 * H * 4), outB = x.host_alloc(2 * H * 4), inA = x.host_alloc(16), outA = x.host_alloc(16), d = dv(); for (let c = 0; c < 2; c++) { d.setBigUint64(inA + c * 8, BigInt(inB + c * H * 4), true); d.setBigUint64(outA + c * 8, BigInt(outB + c * H * 4), true); } return { inB, outB, inA, outA }; };
    const auds = effs.map(mkAudio); const chunks0 = []; let balChunks = [];
    const t0 = performance.now();
    for (let b = 0; b < nblk; b++) for (let k = 0; k < effs.length; k++) {
      const au = auds[k], f = new Float32Array(x.memory.buffer, au.inB, 2 * H);
      for (let i = 0; i < H; i++) { f[i] = Math.fround(Math.sin((i + b * H) * 0.05) * 0.7 + Math.sin((i + b * H) * 0.011) * 0.3); f[H + i] = Math.fround(Math.cos((i + b * H) * 0.13) * 0.5); }
      x.host_process(effs[k], au.inA, au.outA, H);
      if (k === 0) chunks0.push(new Uint8Array(x.memory.buffer.slice(au.outB, au.outB + 2 * H * 4)));
      if (k === nmod && b === 0) balChunks.push(new Uint8Array(x.memory.buffer.slice(au.outB, au.outB + 2 * H * 4)));
    }
    R.interleave_ms = performance.now() - t0;
    const all = new Uint8Array(chunks0.length * 2 * H * 4); chunks0.forEach((c, i) => all.set(c, i * 2 * H * 4));
    R.ott0_sha256 = await sha256(all); R.bal_first_block_sha256 = await sha256(balChunks[0]);
    // 128 frame 1 処理の実時間 (OTT 単独 = effs[0]・ウォームアップ 50 回後に 1000 回計測)
    { const au = auds[0], f = new Float32Array(x.memory.buffer, au.inB, 2 * H); for (let i = 0; i < 2 * H; i++) f[i] = 0.1;
      for (let i = 0; i < 50; i++) x.host_process(effs[0], au.inA, au.outA, H);
      const ts2 = []; for (let i = 0; i < 1000; i++) { const s = performance.now(); x.host_process(effs[0], au.inA, au.outA, H); ts2.push(performance.now() - s); }
      ts2.sort((a, b) => a - b); R.frame128 = { n: ts2.length, median_ms: ts2[500], p99_ms: ts2[990], min_ms: ts2[0], budget_ms: H / 44100 * 1000 }; }
    // 追加 instance 生成: Memory 個数/時間 (lowbase 24MiB initial / 64MiB max)
    const keep = []; const ts = performance.now();
    try { for (let i = 0; i < nspawn; i++) keep.push(await ottF()); } catch (e) { R.spawn_error = String(e.message || e).slice(0, 120); }
    R.spawn = { requested: nspawn, created: keep.length, ms: performance.now() - ts };
    R.spawn_linear_mib_total = keep.reduce((a, m) => a + m.HEAPU8.length, 0) / 1048576;
  } catch (e) { R.errors.push(String(e && e.stack || e)); }
  postMessage(R);
};
