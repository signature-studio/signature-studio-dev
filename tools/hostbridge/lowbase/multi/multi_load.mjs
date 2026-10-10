// multi_load.mjs — 複数 module 同時ロード試験 (hostbridge ホスト 1 つ + HostBridge 1 つに N 個の wasm module を載せる).
//   node multi_load.mjs --ott <ott_hb.cjs> --nmod 4 [--bal <bal_hb.cjs>] [--out result.json] [--label lb|orig]
//   各 OTT module は独立した wasm instance = 専用 linear memory (id/alias を変えて ModuleTable に別 module として登録; 同一 .wasm の 1 DLL = 1 instance)。
//   測定: /proc/self/status の VmRSS / VmData (committed 私的領域) / VmSize、linear memory 合計 (HEAPU8.length)。
//   出力検査: 全 OTT module が同一入力に同一 bit 出力 / bal module は native 機械語 (tools/plugins t0_balance の native_ref) と一致。
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const POC = path.join(HERE, '../../poc');
const { ModuleTable, HostBridge, EmscriptenGuest } = await import(path.join(POC, 'hb_bridge.mjs'));
const require = createRequire(import.meta.url);
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const OTT = arg('ott'), BAL = arg('bal'), NMOD = Number(arg('nmod', 4)), OUT = arg('out'), LABEL = arg('label', 'lb');
const HOSTWASM = arg('host', path.join(HERE, '../work/hb_0x10000/host_vst2.wasm'));
const NATIVE_REF = arg('native-ref', path.join(HERE, '../../../plugins/work/balance/native_ref'));
const BAL_DLL = '/home/ubuntu/work/analysis/win64/extracted/block18983_PE.bin';
const SR = 44100, NCH = 2, HALF = 128, NBLK = 500;

const st = () => { const t = fs.readFileSync('/proc/self/status', 'utf8'); const g = (k) => Number(t.match(new RegExp(k + ':\\s+(\\d+) kB'))[1]) / 1024; return { rss: g('VmRSS'), vmdata: g('VmData'), vmsize: g('VmSize') }; };
const checks = []; const ck = (n, c, x = '') => { checks.push({ name: n, ok: !!c, extra: String(x) }); console.log(c ? 'OK  ' : 'FAIL', n, x); };
const result = { label: LABEL, nmod: NMOD, mem: {}, checks };
const m0 = st(); result.mem.base = m0;

class Host {
  constructor(bridge) { this.bridge = bridge; this.inst = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(HOSTWASM)), bridge.imports()); bridge.attachHost(this.inst); this.x = this.inst.exports; }
  get dv() { return new DataView(this.x.memory.buffer); }
  wstr(s) { const p = this.x.host_alloc(2 * (s.length + 1)); const d = this.dv; for (let i = 0; i < s.length; i++) d.setUint16(p + 2 * i, s.charCodeAt(i), true); d.setUint16(p + 2 * s.length, 0, true); return p; }
  load(p) { return this.x.host_load_plugin(this.wstr(p), SR, HALF); }
  mkAudio(n) { const inB = this.x.host_alloc(NCH * n * 4), outB = this.x.host_alloc(NCH * n * 4), inA = this.x.host_alloc(16), outA = this.x.host_alloc(16), d = this.dv;
    for (let c = 0; c < NCH; c++) { d.setBigUint64(inA + c * 8, BigInt(inB + c * n * 4), true); d.setBigUint64(outA + c * 8, BigInt(outB + c * n * 4), true); } return { inB, outB, inA, outA, n }; }
}
const fillIn = (f, n, ph) => { for (let i = 0; i < n; i++) { f[i] = Math.fround(Math.sin((i + ph) * 0.05) * 0.7 + Math.sin((i + ph) * 0.011) * 0.3); f[n + i] = Math.fround(Math.cos((i + ph) * 0.13) * 0.5); } };

function makeDesc(id, alias, name, vendor, cjs, count) {
  const factory = require(cjs); const pool = [];
  const d = { id, name, vendor, format: 'vst2', arch: 'x64', aliases: [alias], exports: { VSTPluginMain: 'VSTPluginMain', main: 'VSTPluginMain' }, guests: pool,
    async prewarm(n) { for (let i = 0; i < n; i++) pool.push(new EmscriptenGuest(await factory())); },
    acquire() { const g = pool.pop(); if (!g) throw new Error('pool empty'); d.live = g; return g; }, release() {}, poolSize: () => pool.length };
  return d;
}

// ---- prewarm: NMOD 個の OTT module (各々専用 linear memory) ----
const descs = [];
for (let k = 0; k < NMOD; k++) { const d = makeDesc(`xfer.ott.vst2#${k}`, `OTT${k}_x64.dll`, 'OTT', 'Xfer Records', OTT); await d.prewarm(1); descs.push(d); }
const m1 = st(); result.mem.after_ott = m1;
const ottMemBytes = descs.map((d) => d.guests[0].mod.HEAPU8.length);
result.mem.ott_linear_bytes_each = ottMemBytes[0]; result.mem.ott_linear_bytes_sum = ottMemBytes.reduce((a, b) => a + b, 0);
let balDesc = null;
if (BAL) { balDesc = makeDesc('imageline.balance.kernel', 'BalanceK_x64.dll', 'Balance kernel', 'Image-Line', BAL); await balDesc.prewarm(1); descs.push(balDesc); }
const m2 = st(); result.mem.after_all = m2;
result.mem.bal_linear_bytes = balDesc ? balDesc.guests[0].mod.HEAPU8.length : 0;
const MiB = (b) => (b / 1048576).toFixed(1);
console.log(`INFO [${LABEL}] OTT linear memory = ${MiB(ottMemBytes[0])} MiB × ${NMOD} = ${MiB(result.mem.ott_linear_bytes_sum)} MiB; balance = ${MiB(result.mem.bal_linear_bytes)} MiB`);
console.log(`INFO RSS ${m0.rss.toFixed(0)} → ${m1.rss.toFixed(0)} (OTT×${NMOD}) → ${m2.rss.toFixed(0)} MB; VmData ${m0.vmdata.toFixed(0)} → ${m1.vmdata.toFixed(0)} → ${m2.vmdata.toFixed(0)} MB; VmSize ${m0.vmsize.toFixed(0)} → ${m2.vmsize.toFixed(0)} MB`);

const table = new ModuleTable(); for (const d of descs) table.register(d);
const bridge = new HostBridge(table); const host = new Host(bridge);
const pathOf = (d) => `C:\\Program Files\\Common Files\\VST2\\${d.vendor}\\${d.aliases[0]}`;
const effs = descs.map((d) => host.load(pathOf(d)));
ck('M1 全 module (OTT×' + NMOD + (balDesc ? ' + Balance kernel' : '') + ') が同一 host / bridge に LoadLibrary 成功', effs.every((e) => e !== 0), effs.map((e) => e).join(','));
ck('M2 各 module は別 wasm instance (別 linear memory)', new Set(descs.map((d) => d.live.mod.HEAPU8.buffer)).size === descs.length);
const m3 = st(); result.mem.after_load = m3;

const nOtt = NMOD;
for (let k = 0; k < nOtt; k++) { for (let i = 0; i < 20; i++) host.x.host_set_param(effs[k], i, i === 19 ? 0 : 0.5); host.x.host_dispatch(effs[k], 12, 0, 1n, 0, 0); }
if (balDesc) { const g = [0.8, 0.5, 0.3, -0.2, 0, 0, 0, 0]; g.forEach((v, i) => host.x.host_set_param(effs[nOtt], i, v)); host.x.host_dispatch(effs[nOtt], 12, 0, 1n, 0, 0); }

// ---- 500 block × 128f を全 module で交互に処理 (AudioWorklet 想定) ----
const auds = effs.map(() => host.mkAudio(HALF));
const hashes = effs.map(() => crypto.createHash('sha256'));
const firstBlock = []; const DUMP = arg('dump'); const dumpChunks = [];
const t0 = process.hrtime.bigint();
for (let b = 0; b < NBLK; b++) {
  for (let k = 0; k < effs.length; k++) {
    const au = auds[k]; fillIn(new Float32Array(host.x.memory.buffer, au.inB, NCH * HALF), HALF, b * HALF);
    host.x.host_process(effs[k], au.inA, au.outA, HALF);
    const o = new Uint8Array(host.x.memory.buffer, au.outB, NCH * HALF * 4);
    hashes[k].update(o); if (DUMP && k === 0) dumpChunks.push(Buffer.from(o));
    if (b === 0) firstBlock[k] = Array.from(new Uint32Array(host.x.memory.buffer.slice(au.outB, au.outB + NCH * HALF * 4)));
    if (b === 0 && k === nOtt && balDesc) result.bal_first_block_sha256 = crypto.createHash('sha256').update(o).digest('hex');
  }
}
const dtms = Number(process.hrtime.bigint() - t0) / 1e6;
if (DUMP) fs.writeFileSync(DUMP, Buffer.concat(dumpChunks));
const hex = hashes.map((h) => h.digest('hex'));
result.ott_sha256_full = hex[0];
result.ott_sha256 = hex.slice(0, nOtt); result.ott_first_block = firstBlock[0];
ck(`M3 OTT×${nOtt} の ${NBLK}blk×${HALF}f 出力 sha256 が全 module で一致 (module 間状態漏れ無し)`, hex.slice(0, nOtt).every((h) => h === hex[0]), hex[0].slice(0, 16));
console.log(`INFO ${NBLK} blocks × ${effs.length} module (interleaved): ${dtms.toFixed(0)} ms (${(dtms * 1000 / NBLK / effs.length).toFixed(1)} µs/blk/module 含 marshal)`);
result.interleave_ms = dtms;
const finishMem = st(); result.mem.after_run = finishMem;

// ---- Balance kernel: native 機械語 (t0_balance native_ref) と一致 ----
if (balDesc) {
  const gs = [[0.8, 0.5, 0.3, -0.2, 0, 0, 0, 0], [0.8, 0.5, 0, 0, 0, 0, 0, 0], [0.8, 0.5, 0.3, -0.2, 0.01, 0.02, 0, 0]];
  const e = effs[nOtt]; const n = HALF; const cases = []; const bufs = [];
  for (const g of gs) {
    g.forEach((v, i) => host.x.host_set_param(e, i, v)); const au = host.mkAudio(n); fillIn(new Float32Array(host.x.memory.buffer, au.inB, 2 * n), n, 77);
    host.x.host_process(e, au.inA, au.outA, n);
    const out = new Float32Array(host.x.memory.buffer.slice(au.outB, au.outB + 8 * n)); const inp = new Float32Array(host.x.memory.buffer.slice(au.inB, au.inB + 8 * n));
    const il = new Float32Array(2 * n + 8); for (let i = 0; i < n; i++) { il[2 * i] = inp[i]; il[2 * i + 1] = inp[n + i]; }
    cases.push({ g, il, out });
  }
  let total = 4; for (const c of cases) total += 24 + 32 + 4 * c.il.length;
  const buf = Buffer.alloc(total); let o = 0; buf.writeUInt32LE(cases.length, o); o += 4;
  for (const c of cases) { for (const v of [0, n, 0, 0, 0, 0]) { buf.writeUInt32LE(v, o); o += 4; } for (let i = 0; i < 8; i++) { buf.writeFloatLE(c.g[i], o); o += 4; } for (const v of c.il) { buf.writeFloatLE(v, o); o += 4; } }
  const W = fs.mkdtempSync('/tmp/opencode/lbbal_'); fs.writeFileSync(W + '/cases.bin', buf);
  execFileSync(NATIVE_REF, [BAL_DLL, W + '/cases.bin', W + '/native.bin']);
  const nat = fs.readFileSync(W + '/native.bin'); let p = 0, eq = 0, tot = 0;
  for (const c of cases) { p += 8; const nw = nat.readUInt32LE(p); p += 4; for (let i = 0; i < 2 * n; i++) { const w = nat.readUInt32LE(p + 4 * i); const hv = new Uint32Array(c.out.buffer)[(i & 1) * n + (i >> 1)]; tot++; if (w === hv) eq++; } p += 4 * nw; }
  ck('M4 Balance kernel (lowbase module) の出力が native 機械語 (DLL@0x400000, ms_abi) と bit 一致 via hostbridge', eq === tot, `${eq}/${tot} cells (${cases.length} gain sets)`);
  result.bal_native_cells = [eq, tot];
}
const broken = checks.filter((c) => !c.ok).length;
result.checks_total = checks.length; result.checks_broken = broken;
if (OUT) fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
console.log(`[multi_load ${LABEL}] checks ${checks.length} / broken ${broken}`);
process.exit(broken ? 1 : 0);
