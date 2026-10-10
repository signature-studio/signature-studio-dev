// run_poc.mjs — hostbridge PoC 検収: mini VST2 host (wasm) ⇄ bridge ⇄ OTT wasm (M10 lift 成果 + 入口 surrogate)
//   node tools/hostbridge/poc/run_poc.mjs   (事前: bash poc/build_plugin_ott.sh, bash poc/build_host.sh)
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { ModuleTable, HostBridge, THUNK_BASE } from './hb_bridge.mjs';
import { makeOttDesc } from './ott_module.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WORK = path.join(HERE, '../work');
const M10_CJS = path.join(HERE, '../../m10/work/ott_m10.cjs');
const require = createRequire(import.meta.url);
const hostMod = new WebAssembly.Module(fs.readFileSync(path.join(WORK, 'host_vst2.wasm')));

const checks = []; const result = { checks: [], metrics: {} };
const ck = (name, cond, extra = '') => { checks.push([name, !!cond]); result.checks.push({ name, ok: !!cond, extra: String(extra) }); console.log(cond ? 'OK  ' : 'FAIL', name, extra); };
const info = (...a) => console.log('INFO', ...a);

const OTT_PATH = 'C:\\Program Files\\Common Files\\VST2\\Xfer Records\\OTT_x64.dll';
const SR = 44100, N = 256, NCH = 2;
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return new Uint32Array(f.buffer)[0]; };

class Host {
  constructor(bridge) {
    this.bridge = bridge;
    this.inst = new WebAssembly.Instance(hostMod, bridge.imports());
    bridge.attachHost(this.inst);
    this.x = this.inst.exports;
  }
  get u8() { return new Uint8Array(this.x.memory.buffer); }
  get dv() { return new DataView(this.x.memory.buffer); }
  wstr(s) { const p = this.x.host_alloc(2 * (s.length + 1)); const d = this.dv; for (let i = 0; i < s.length; i++) d.setUint16(p + 2 * i, s.charCodeAt(i), true); d.setUint16(p + 2 * s.length, 0, true); return p; }
  cstr(p, max = 64) { const u = this.u8; let s = ''; while (max-- > 0 && u[p]) s += String.fromCharCode(u[p++]); return s; }
  load(p, sr = SR, block = N) { return this.x.host_load_plugin(this.wstr(p), sr, block); }
  info() {
    const b = this.x.host_info(), d = this.dv;
    return { name: this.cstr(b), vendor: this.cstr(b + 64), product: this.cstr(b + 128), vstVersion: d.getInt32(b + 192, true), category: d.getInt32(b + 196, true),
      vendorVersion: d.getInt32(b + 200, true), numPrograms: d.getInt32(b + 204, true), numParams: d.getInt32(b + 208, true), numInputs: d.getInt32(b + 212, true),
      numOutputs: d.getInt32(b + 216, true), flags: d.getInt32(b + 220, true), uniqueID: d.getInt32(b + 224, true) >>> 0, version: d.getInt32(b + 228, true),
      getProcTries: d.getInt32(b + 232, true), magicOk: d.getInt32(b + 236, true), am: (op) => d.getInt32(b + 240 + op * 4, true), hmodule: d.getBigUint64(b + 504, true) };
  }
  mkAudio(n) { // in/out float** (Win64: 8B ポインタ) を host memory に用意
    const inB = this.x.host_alloc(NCH * n * 4), outB = this.x.host_alloc(NCH * n * 4), inA = this.x.host_alloc(16), outA = this.x.host_alloc(16), d = this.dv;
    for (let c = 0; c < NCH; c++) { d.setBigUint64(inA + c * 8, BigInt(inB + c * n * 4), true); d.setBigUint64(outA + c * 8, BigInt(outB + c * n * 4), true); }
    return { inB, outB, inA, outA, n };
  }
  fill(au) { const f = new Float32Array(this.x.memory.buffer, au.inB, NCH * au.n); fillInput(f, au.n); }
  outBits(au) { const o = new Uint32Array(this.x.memory.buffer, au.outB, NCH * au.n); return Array.from(o); }
  ptrs(au, off) { // 窓 (off サンプル目) 用 float** を作る
    const d = this.dv, a = this.x.host_alloc(16), b = this.x.host_alloc(16);
    for (let c = 0; c < NCH; c++) { d.setBigUint64(a + c * 8, BigInt(au.inB + (c * au.n + off) * 4), true); d.setBigUint64(b + c * 8, BigInt(au.outB + (c * au.n + off) * 4), true); }
    return [a, b];
  }
}
function fillInput(f, n) { // m10_e2e.sh fillInputs() と同一
  for (let i = 0; i < n; i++) { f[i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); f[n + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
}
const paramVal = (i) => (i === 19 ? 0 : 0.5);

// ---- 直接呼出 baseline (bridge を経由しない). 同一 wasm の lift 関数を、bridge 経路と同じ順序で直叩き ----
async function directBaseline(blocks) {
  const mod = await require(path.join(WORK, 'ott_hb.cjs'))();
  mod._m6_data_install();
  const OBJ = 0x30600000, BUF = 0x30620000, U8 = mod.HEAPU8, U32 = mod.HEAPU32, dv = new DataView(U8.buffer);
  mod._function_18011d400(BigInt(OBJ), 0n); mod._function_180120800(BigInt(OBJ));
  dv.setFloat32(OBJ + 0x18, SR, true); dv.setInt32(OBJ + 0x1c, N, true); mod._function_180120800(BigInt(OBJ));
  for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), BigInt(f32b(paramVal(i))));
  mod._function_180120800(BigInt(OBJ));
  const IN_A = 0x30610000, OU_A = 0x30611000, n = N;
  fillInput(new Float32Array(U8.buffer, BUF, 2 * n), n);
  for (const b of blocks) { // b = [off, len]
    U32[IN_A / 4] = BUF + b[0] * 4; U32[IN_A / 4 + 2] = BUF + n * 4 + b[0] * 4;
    U32[OU_A / 4] = BUF + n * 8 + b[0] * 4; U32[OU_A / 4 + 2] = BUF + n * 12 + b[0] * 4;
    mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(b[1]));
  }
  const bits = []; for (let c = 0; c < 2; c++) for (let i = 0; i < n; i++) bits.push(U32[(BUF + n * (8 + 4 * c)) / 4 + i]);
  return { bits };
}
// ---- M10 の正規手順 (m10_e2e.sh setup(0.5)): ctor → params → resume ----
async function m10Canonical() {
  const mod = await require(M10_CJS)();
  mod._m6_data_install();
  const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, U8 = mod.HEAPU8, U32 = mod.HEAPU32;
  mod._function_18011d400(BigInt(OBJ), 0n);
  for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), BigInt(f32b(paramVal(i))));
  mod._function_180120800(BigInt(OBJ)); U8[OBJ + 0x248] = 0;
  fillInput(new Float32Array(U8.buffer, BUF, 2 * N), N);
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
  mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const bits = []; for (let c = 0; c < 2; c++) for (let i = 0; i < N; i++) bits.push(U32[(BUF + N * (8 + 4 * c)) / 4 + i]);
  return bits;
}
const ndiff = (a, b) => { let d = 0; for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d++; return d; };
const census = (bits) => { const f = new Float32Array(new Uint32Array(bits).buffer); let z = 0, nrm = 0, hi = 0, tiny = 0, nan = 0; for (const v of f) { const a = Math.abs(v); if (v === 0) z++; else if (Number.isNaN(v)) nan++; else if (a >= 4) hi++; else if (a <= 1e-18) tiny++; else nrm++; } return { zero: z, normal: nrm, junkHi: hi, junkTiny: tiny, nan }; };

// =============================== main ===============================
const t0 = Date.now();
const ott = makeOttDesc();
await ott.prewarm(3);
const rss0 = process.memoryUsage().rss / 1048576;
info(`prewarm 3 instances: ${Date.now() - t0} ms (instancesCreated=${ott.instancesCreated}) node RSS=${rss0.toFixed(0)} MB (各 instance の linear memory = 864 MiB 予約)`);
result.metrics.prewarm_ms = Date.now() - t0; result.metrics.rss_after_prewarm_mb = Math.round(rss0);
const table = new ModuleTable().register(ott);

// ---- T0 レジストリ / 仮想 VST フォルダ ----
{
  const vp = table.virtualPaths();
  ck('T0a registry: 仮想 VST パス列挙', vp.length === 1 && vp[0].path.endsWith('Xfer Records\\OTT_x64.dll'), vp[0].path);
  ck('T0b registry: 別パス表記(小文字/スラッシュ/ディレクトリ違い)でも同一 module に解決', table.resolve('d:/vst/ott_x64.DLL') === ott && table.resolve('/Library/Audio/Plug-Ins/VST/OTT.vst') === null);
}

const bridge = new HostBridge(table);
bridge.trace = (m) => info('[shim]', m);
const host = new Host(bridge);

// ---- T1 否定系 ----
{
  const h = bridge.LoadLibraryW(host.wstr('C:\\nowhere\\Missing_x64.dll'));
  ck('T1a LoadLibraryW(未登録) = NULL / GetLastError=126', h === 0n && bridge.lastError === 126);
  const e = host.x.host_load_plugin(host.wstr('C:\\nowhere\\Missing_x64.dll'), SR, N);
  ck('T1b host_load_plugin(未登録) = NULL', e === 0);
}

// ---- T2 ロード手順 (Fruity Wrapper TVSTPlugin.Create 再現) ----
const eff = host.load(OTT_PATH);
const I = host.info();
info('plugin info:', JSON.stringify({ ...I, am: undefined, hmodule: String(I.hmodule) }));
ck('T2a LoadLibraryW→GetProcAddress→main→magic "VstP" 検査 OK', eff !== 0 && I.magicOk === 1);
ck('T2b GetProcAddress 試行 2 回 (VstPluginMain 不在 → VSTPluginMain 命中; 26 名前表)', I.getProcTries === 2, `tries=${I.getProcTries}`);
ck('T2c effGetEffectName/Vendor/Product = OTT / Xfer Records / OTT', I.name === 'OTT' && I.vendor === 'Xfer Records' && I.product === 'OTT', `${I.name}/${I.vendor}/${I.product}`);
ck('T2d uniqueID = "XfTT" (lift 済み ctor が書いた値)', I.uniqueID === 0x58665454, '0x' + I.uniqueID.toString(16));
ck('T2e AEffect: numInputs=numOutputs=2, numParams=20, numPrograms=1, flags∋CanReplacing, HasEditor 無', I.numInputs === 2 && I.numOutputs === 2 && I.numParams === 20 && I.numPrograms === 1 && (I.flags & 0x10) && !(I.flags & 1), `flags=0x${I.flags.toString(16)}`);
ck('T2f effGetVstVersion=2400, effGetPlugCategory=1, vendorVersion=1037', I.vstVersion === 2400 && I.category === 1 && I.vendorVersion === 1037);
ck('T2g upcall: audioMasterVersion×1 (VSTPluginMain 内) + audioMasterGetSampleRate×1 (effOpen 内)', I.am(1) === 1 && I.am(16) === 1, `am[1]=${I.am(1)} am[16]=${I.am(16)}`);
ck('T2h AEffect 関数ポインタは bridge の合成 VA (host から guest コード直アクセス不可)', (() => { const d = host.dv; return [8, 0x18, 0x20, 0x78].every((o) => d.getBigUint64(eff + o, true) >= THUNK_BASE); })());
{ const d = host.dv, g = bridge.loaded.get('xfer.ott.vst2').guest; ck('T2i resvd1(host 所有) が guest 側 AEffect にも mirror される', g.dv.getBigUint64(bridge.proxy.get(eff).pe + 0x40, true) === d.getBigUint64(eff + 0x40, true) && d.getBigUint64(eff + 0x40, true) !== 0n); }
const names = []; { const b = host.x.host_alloc(600); for (let i = 0; i < 20; i++) { host.x.host_param_name(eff, i, b); names.push(host.cstr(b, 600)); } }
ck('T2j effGetParamName ×20 (marshal outstr)', names[0] === 'Depth' && names[17] === 'Upwd Strgth' && names[18] === 'Dnwd Strgth', names.slice(0, 4).join('|') + '…');

// ---- T3 param 往復 ----
for (let i = 0; i < 20; i++) host.x.host_set_param(eff, i, paramVal(i));
ck('T3a setParameter/getParameter 往復 (f32 ビット保存)', host.x.host_get_param(eff, 3) === 0.5 && host.x.host_get_param(eff, 19) === 0);
{ const b = host.x.host_alloc(64); host.x.host_param_display(eff, 3, b); ck('T3b effGetParamDisplay marshal', host.cstr(b) === '0.50', host.cstr(b)); }

// ---- T4 processReplacing: bridge 経由 vs 直接 baseline (同一手順) ----
host.x.host_dispatch(eff, 12, 0, 1n, 0, 0); // effMainsChanged(1) → resume (params 設定後 = baseline と同順)
const au = host.mkAudio(N); host.fill(au);
host.x.host_process(eff, au.inA, au.outA, N);
const bridged = host.outBits(au);
const base = await directBaseline([[0, N]]);
const d4 = ndiff(bridged, base.bits);
const c4 = census(bridged);
ck('T4a bridge 経由 processReplacing(256) = 直接 baseline と 512/512 bit 一致', d4 === 0, `diff cells=${d4}/${bridged.length}`);
ck('T4b 出力が非自明 (全 0 でも NaN でもない)', c4.zero < 512 && c4.nan === 0, JSON.stringify(c4));
const m10 = await m10Canonical();
{ // 参考: M10 e2e 正規手順との比較 (resume 回数/順序差 + [0x248] 既定値差を含む)
  const d = ndiff(bridged, m10);
  info(`M10 正規手順 (ctor→params→resume→[0x248]=0→process) との差分 cell = ${d}/512; census(bridged)=${JSON.stringify(c4)} census(m10)=${JSON.stringify(census(m10))}`);
  result.metrics.diff_vs_m10_canonical = d; result.metrics.census_bridged = c4; result.metrics.census_m10 = census(m10);
  const gI = bridge.proxy.get(eff), gg = bridge.loaded.get('xfer.ott.vst2').guest, objA = Number(gg.dv.getBigUint64(gI.pe + 0x60, true));
  result.metrics.flag248_default = gg.u8[objA + 0x248];
  info(`bridge 経路の obj+0x248 既定値 = ${gg.u8[objA + 0x248]} (M10 e2e は process 前に 0 へ強制)`);
}
{ // M10 と同条件 ([0x248]=0 を guest memory へ poke) で bridge 経由 → M10 正規出力と比較
  const e5 = host.load(OTT_PATH);
  for (let i = 0; i < 20; i++) host.x.host_set_param(e5, i, paramVal(i));
  host.x.host_dispatch(e5, 12, 0, 1n, 0, 0);
  const gI = bridge.proxy.get(e5), gg = bridge.loaded.get('xfer.ott.vst2').guest, objA = Number(gg.dv.getBigUint64(gI.pe + 0x60, true));
  gg.u8[objA + 0x248] = 0;
  const a5 = host.mkAudio(N); host.fill(a5); host.x.host_process(e5, a5.inA, a5.outA, N);
  const b5 = host.outBits(a5), d5 = ndiff(b5, m10);
  ck('T4c [0x248]=0 poke 後の bridge 出力 = M10 e2e 正規手順の出力 (M10 到達水準と同一)', d5 === 0, `diff cells vs M10=${d5}/512 census=${JSON.stringify(census(b5))}`);
  result.metrics.diff_vs_m10_flag0 = d5;
  host.x.host_close(e5);
}
// 2 本目 instance (同一 DLL → refcount=2, 別 AEffect)
const eff2 = host.load(OTT_PATH);
const I2 = host.info();
ck('T5a 2 本目 LoadLibraryW は同一 HMODULE (refcount=2) / 別 AEffect proxy', I2.hmodule === I.hmodule && eff2 !== eff && eff2 !== 0);
for (let i = 0; i < 20; i++) host.x.host_set_param(eff2, i, paramVal(i));
host.x.host_dispatch(eff2, 12, 0, 1n, 0, 0);
const au2 = host.mkAudio(N); host.fill(au2);
host.x.host_process(eff2, au2.inA, au2.outA, N);
ck('T5b 2 本目 instance の出力 = 1 本目と bit 一致 (instance 間状態漏れ無し)', ndiff(host.outBits(au2), bridged) === 0);
// A/B 交互に 2×128 (AudioWorklet 128f) → 直接 2×128 baseline と一致
{
  const half = 128, auA = host.mkAudio(N), auB = host.mkAudio(N); host.fill(auA); host.fill(auB);
  const effA = host.load(OTT_PATH), effB = host.load(OTT_PATH);
  for (const e of [effA, effB]) { for (let i = 0; i < 20; i++) host.x.host_set_param(e, i, paramVal(i)); host.x.host_dispatch(e, 12, 0, 1n, 0, 0); }
  for (const off of [0, half]) for (const [e, a] of [[effA, auA], [effB, auB]]) { const [pi, po] = host.ptrs(a, off); host.x.host_process(e, pi, po, half); }
  const bA = host.outBits(auA), bB = host.outBits(auB);
  const baseHalf = await directBaseline([[0, half], [half, half]]);
  ck('T5c A/B 交互 2×128 (AudioWorklet 128f) = 直接 2×128 baseline と bit 一致', ndiff(bA, baseHalf.bits) === 0 && ndiff(bB, baseHalf.bits) === 0, `diffA=${ndiff(bA, baseHalf.bits)} diffB=${ndiff(bB, baseHalf.bits)}`);
  const dBlk = ndiff(bA, bridged);
  info(`ブロック分割依存: 2×128 と 1×256 の出力差分 cell = ${dBlk}/512 (lift 側の block 依存性; bridge 無関係)`);
  result.metrics.block_split_dependence_cells = dBlk;
  for (const e of [effA, effB]) host.x.host_close(e);
}
host.x.host_close(eff2);
ck('T6a FreeLibrary refcount: eff が保持中 → module は残存', bridge.loaded.has('xfer.ott.vst2') && bridge.loaded.get('xfer.ott.vst2').refs === 1, `refs=${bridge.loaded.get('xfer.ott.vst2')?.refs}`);

// ---- T7 性能: 128 frame/call ----
{
  const half = 128, [a, b] = host.ptrs(au, 0);
  const ITER = 3000;
  for (let i = 0; i < 200; i++) host.x.host_process(eff, a, b, half);
  let t = process.hrtime.bigint();
  for (let i = 0; i < ITER; i++) host.x.host_process(eff, a, b, half);
  const brUs = Number(process.hrtime.bigint() - t) / 1000 / ITER;
  // 直接: bridge をバイパスして guest の hb_icall を直叩き (marshal 無し)
  const g = bridge.loaded.get('xfer.ott.vst2').guest, inst = bridge.proxy.get(eff);
  const gin = g.space.alloc(16), gout = g.space.alloc(16), bytes = half * 4, gp = [0, 1, 2, 3].map(() => g.space.alloc(bytes));
  g.dv.setBigUint64(gin, BigInt(gp[0]), true); g.dv.setBigUint64(gin + 8, BigInt(gp[1]), true); g.dv.setBigUint64(gout, BigInt(gp[2]), true); g.dv.setBigUint64(gout + 8, BigInt(gp[3]), true);
  const pfn = bridge.slotOf(inst.fnVA.processReplacing).pfn;
  for (let i = 0; i < 200; i++) g.call(pfn, [inst.pe, gin, gout, half]);
  t = process.hrtime.bigint();
  for (let i = 0; i < ITER; i++) g.call(pfn, [inst.pe, gin, gout, half]);
  const dirUs = Number(process.hrtime.bigint() - t) / 1000 / ITER;
  const budget = (half / SR) * 1e6;
  info(`processReplacing 128f: bridge 経由 ${brUs.toFixed(1)} µs/call, guest 直 ${dirUs.toFixed(1)} µs/call, marshal 差 ${(brUs - dirUs).toFixed(1)} µs (${((brUs - dirUs) / budget * 100).toFixed(2)}% of ${budget.toFixed(0)} µs budget)`);
  Object.assign(result.metrics, { bridged_us_per_128f: +brUs.toFixed(2), direct_us_per_128f: +dirUs.toFixed(2), marshal_overhead_us: +(brUs - dirUs).toFixed(2), budget_us_128f: +budget.toFixed(1) });
  ck('T7 marshal 差分が 128f RT 予算の 10% 未満', (brUs - dirUs) < budget * 0.1);
  // 固定コスト: DSP 無しの getParameter で bridge 往復 (host wasm → import → slot → sync → guest → 戻り) を測る
  const IT2 = 100000; const gpfn = bridge.slotOf(inst.fnVA.getParameter).pfn;
  for (let i = 0; i < 2000; i++) host.x.host_get_param(eff, 3);
  t = process.hrtime.bigint(); for (let i = 0; i < IT2; i++) host.x.host_get_param(eff, 3); const gbr = Number(process.hrtime.bigint() - t) / 1000 / IT2;
  t = process.hrtime.bigint(); for (let i = 0; i < IT2; i++) g.call(gpfn, [inst.pe, 3]); const gdr = Number(process.hrtime.bigint() - t) / 1000 / IT2;
  info(`getParameter 往復: bridge 経由 ${gbr.toFixed(2)} µs, guest 直 ${gdr.toFixed(2)} µs → 固定オーバーヘッド ≈ ${(gbr - gdr).toFixed(2)} µs/call`);
  Object.assign(result.metrics, { getparam_bridged_us: +gbr.toFixed(3), getparam_direct_us: +gdr.toFixed(3), fixed_overhead_us: +(gbr - gdr).toFixed(3) });
}

// ---- T8 fail-fast / 規則無し opcode ----
{
  let threw = false; try { bridge.icall(0x1234n, [0n, 0n, 0n, 0n, 0n, 0n]); } catch (e) { threw = /invalid guest function pointer/.test(e.message); }
  ck('T8a 不正関数ポインタ icall は fail-fast', threw);
  const before = bridge.stats.unmarshalled; const p = host.x.host_alloc(16);
  host.x.host_dispatch(eff, 9999, 0, 0n, p, 0); // 規則の無い opcode に host ポインタ → guest へは渡さない
  ck('T8b 規則の無い opcode の host ポインタは guest へ渡さず計上', bridge.stats.unmarshalled === before + 1);
}

// ---- 後始末: FreeLibrary 全解放 → 再ロードで fresh instance ----
host.x.host_close(eff);
ck('T6b 全 FreeLibrary 後 module 解放', !bridge.loaded.has('xfer.ott.vst2') && bridge.loaded.size === 0, `loaded=${bridge.loaded.size}`);
{
  const pre = ott.poolSize(); const e3 = host.load(OTT_PATH);
  ck('T6c 解放後の再 LoadLibrary は新規 instance (pool から)', e3 !== 0 && ott.poolSize() === pre - 1, `pool ${pre}→${ott.poolSize()}`);
  host.x.host_close(e3);
}
result.metrics.rss_end_mb = Math.round(process.memoryUsage().rss / 1048576);
result.metrics.bridge_stats = bridge.stats;
info('bridge stats:', JSON.stringify(bridge.stats));

const broken = checks.filter(([, c]) => !c).length;
console.log(`[run_poc] checks ${checks.length} / broken ${broken}`);
fs.writeFileSync(path.join(WORK, 'poc_result.json'), JSON.stringify(result, null, 1));
process.exit(broken ? 1 : 0);
