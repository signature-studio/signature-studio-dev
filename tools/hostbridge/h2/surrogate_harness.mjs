// surrogate_harness.mjs — HB-H2 (CAB-91): lift 済み VSTPluginMain を hostbridge 経由で駆動する surrogate ハーネス。
//
//   node surrogate_harness.mjs --nat tools/hostbridge/h2/work/natref.json [--out result.json]
//
// 構成: mini VST2 host (poc/host_vst2.c 由来 wasm, 別 instance/別 linear memory)
//       ⇄ HostBridge (poc/hb_bridge.mjs — LoadLibrary/GetProcAddress shim + VST2 marshal)
//       ⇄ OTT module (h2/work/ott_h2.cjs — lowbase LB_BASE=0x10000 の入口拡張 x64c lift + vst_module_entry.c glue)
//
// 旧 surrogate (poc/plugin_ott_entry.c) の plugin ロジック再現は撤去済み。AEffect の関数ポインタは
// lift 済み ctor が書いた実 guest VA であり、host からの全呼出が hb_icall → ott_run で lift 済みコードに落ちる。
// 検証は native 実機械語の参照値 (entry_nat.py の出力) との値突合を含む。
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { ModuleTable, HostBridge } from '../poc/hb_bridge.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const NATREF = arg('nat', path.join(HERE, 'work/natref.json'));
const OUT = arg('out', path.join(HERE, 'work/h2_result.json'));
const SR = 44100, HALF = 128;
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const bits2f = (b) => { const u = new Uint32Array([Number(BigInt.asUintN(32, b))]); return new Float32Array(u.buffer)[0]; };

const checks = []; const metrics = {};
const ck = (name, cond, extra = '') => { checks.push({ name, ok: !!cond, extra: String(extra) }); console.log(cond ? 'OK  ' : 'FAIL', name, extra); };

// ---- module desc (poc/ott_module.mjs の低メモリ版) ----
function makeDesc() {
  const factory = require(path.join(HERE, 'work/ott_h2.cjs'));
  const pool = [];
  const d = {
    id: 'xfer.ott.vst2.h2', name: 'OTT', vendor: 'Xfer Records', format: 'vst2', arch: 'x64',
    aliases: ['OTT_x64.dll'], exports: { VSTPluginMain: 'VSTPluginMain', main: 'VSTPluginMain' }, guests: pool,
    async prewarm(n) { for (let i = 0; i < n; i++) pool.push(new (await import('../poc/hb_bridge.mjs')).EmscriptenGuest(await factory())); },
    acquire() { const g = pool.pop(); if (!g) throw new Error('pool empty'); d.live = g; return g; },
    release() {}, poolSize: () => pool.length,
  };
  return d;
}

const desc = makeDesc();
await desc.prewarm(12);
const table = new ModuleTable().register(desc);
const bridge = new HostBridge(table);

const hostMod = new WebAssembly.Module(fs.readFileSync(path.join(HERE, 'work/host_vst2.wasm')));
const host = {
  inst: new WebAssembly.Instance(hostMod, bridge.imports()),
};
bridge.attachHost(host.inst);
host.x = host.inst.exports;
host.dv = new DataView(host.inst.exports.memory.buffer);
host.wstr = (s) => { const p = host.x.host_alloc(2 * (s.length + 1)); for (let i = 0; i < s.length; i++) host.dv.setUint16(p + 2 * i, s.charCodeAt(i), true); host.dv.setUint16(p + 2 * s.length, 0, true); return p; };
host.cstr = (p, max = 600) => { const u = new Uint8Array(host.x.memory.buffer); let s = ''; while (max-- > 0 && u[p]) s += String.fromCharCode(u[p++]); return s; };
host.mkAudio = (n) => {
  const inB = host.x.host_alloc(2 * n * 4), outB = host.x.host_alloc(2 * n * 4), inA = host.x.host_alloc(16), outA = host.x.host_alloc(16);
  host.dv.setBigUint64(inA, BigInt(inB), true); host.dv.setBigUint64(inA + 8, BigInt(inB + n * 4), true);
  host.dv.setBigUint64(outA, BigInt(outB), true); host.dv.setBigUint64(outA + 8, BigInt(outB + n * 4), true);
  return { inB, outB, inA, outA, n };
};
host.fill = (au, phase = 0) => {  // entry_nat.py の proc 入力と同一 byte 列 (inL+inR = n*2*4 byte)
  const u8 = new Uint8Array(host.x.memory.buffer, au.inB, au.n * 2 * 4);
  for (let i = 0; i < u8.length; i++) u8[i] = i % 256;
};
host.outBits = (au) => Array.from(new Uint32Array(host.x.memory.buffer.slice(au.outB, au.outB + au.n * 8)));
host.load = (p, sr = SR, block = 1024) => host.x.host_load_plugin(host.wstr(p), sr, block);
host.info = () => {
  const b = host.x.host_info(), d = host.dv;
  return { name: host.cstr(b), vendor: host.cstr(b + 64), product: host.cstr(b + 128),
    vstVersion: d.getInt32(b + 192, true), category: d.getInt32(b + 196, true), vendorVersion: d.getInt32(b + 200, true),
    numPrograms: d.getInt32(b + 204, true), numParams: d.getInt32(b + 208, true), numInputs: d.getInt32(b + 212, true),
    numOutputs: d.getInt32(b + 216, true), flags: d.getInt32(b + 220, true), uniqueID: d.getInt32(b + 224, true) >>> 0,
    version: d.getInt32(b + 228, true), magicOk: d.getInt32(b + 236, true), am: (op) => d.getInt32(b + 240 + op * 4, true) };
};

const OTT_PATH = 'C:\\Program Files\\Common Files\\VST2\\Xfer Records\\OTT_x64.dll';
const NAT = JSON.parse(fs.readFileSync(NATREF))['scenarios'];
const natCall = (scen, i) => NAT[scen]['calls'][i];
const natCStr = (scen, i) => { const h = natCall(scen, i)['buf']; return Buffer.from(h, 'hex').toString('latin1').split('\x00')[0]; };

// ---- bridge 直接駆動用ヘルパ (host.load の固定 flow を介さず native 参照と同一の呼出列を組む) ----
function load() {
  const h = bridge.LoadLibraryW(host.wstr(OTT_PATH));
  const slot = bridge.GetProcAddress(h, 'VSTPluginMain');
  const proxy = Number(bridge.icall(slot, [BigInt(AM_TIDX)]));
  return { h, proxy };
}
function slotOf(proxy, off) { return host.dv.getBigUint64(proxy + off, true); }
const disp = (proxy, op, idx, val, ptr, opt) => bridge.icall(slotOf(proxy, 8), [BigInt(proxy), BigInt(op), BigInt(idx), BigInt(val ?? 0), BigInt(ptr ?? 0), opt === undefined ? 0n : (typeof opt === 'bigint' ? opt : f32b(opt))]);
const setP = (proxy, idx, v) => bridge.icall(slotOf(proxy, 0x18), [BigInt(proxy), BigInt(idx), f32b(v)]);
const getP = (proxy, idx) => bridge.icall(slotOf(proxy, 0x20), [BigInt(proxy), BigInt(idx)]);
const proc = (proxy, au, n) => bridge.icall(slotOf(proxy, 0x78), [BigInt(proxy), BigInt(au.inA), BigInt(au.outA), BigInt(n)]);

// host_audio_master の table index を取得 (host_vst2.c が &host_audio_master を icall に渡すのと同じ値)
let AM_TIDX = 1; // フォールバック
{
  const t = host.inst.exports.__indirect_function_table;
  for (let i = 0; i < t.length; i++) { if (t.get(i) === host.x.host_audio_master) { AM_TIDX = i; break; } }
}

// ============================== G1: ロード (Fruity Wrapper flow) ==============================
const eff = host.load(OTT_PATH, SR, 1024);
const I = host.info();
ck('G1a LoadLibraryW→GetProcAddress→VSTPluginMain→magic "VstP"', eff !== 0 && I.magicOk === 1);
ck('G1b AEffect: numPrograms=1 numParams=20 numInputs=2 numOutputs=2 (lift 済み ctor が書いた値)', I.numPrograms === 1 && I.numParams === 20 && I.numInputs === 2 && I.numOutputs === 2);
ck('G1c uniqueID="XfTT" version=1 flags=0x18 (CanReplacing|CanMono, HasEditor 無 = editor NULL surrogate)', I.uniqueID === 0x58665454 && I.version === 1 && I.flags === 0x18, 'flags=0x' + I.flags.toString(16));
ck('G1d upcall: audioMasterVersion (VSTPluginMain 内) が host に届く', I.am(1) >= 1, `am[1]=${I.am(1)}`);
ck('G1e effGetEffectName/Vendor/Product = 実 lift の文字列', I.name === 'OTT' && I.vendor === 'Xfer Records' && I.product === 'OTT', `${I.name}/${I.vendor}/${I.product}`);
ck('G1f vstVersion=2400 category=1 vendorVersion = native (op49) と一致', I.vstVersion === 2400 && I.category === 1 && I.vendorVersion === (typeof natCall('op49', 1).rax === 'string' ? parseInt(natCall('op49', 1).rax) : natCall('op49', 1).rax), `ver=${I.vstVersion} vendorVer=${I.vendorVersion}`);

// ---- G2: getParameter (native 参照 = getp_range の xmm0) ----
{
  const eff2 = host.load(OTT_PATH, SR, 1024);
  let ok = 0; const bad = [];
  for (let i = 0; i < 20; i++) {
    const nat = typeof natCall('getp_range', i + 1).xmm0 === 'string' ? parseInt(natCall('getp_range', i + 1).xmm0) : natCall('getp_range', i + 1).xmm0;
    const got = Number(BigInt.asUintN(32, getP(eff2, i)));
    if (got === nat) ok++; else bad.push(`p${i}:${got}≠${nat}`);
  }
  ck('G2 getParameter ×20 (ctor 既定値, xmm0 返値) = native 実機械語と全 bit 一致', ok === 20, ok === 20 ? '20/20' : bad.join(' ').slice(0, 120));
  host.x.host_close(eff2);
}

// ---- G3: setParameter → getParameter 往復 (bridge 経由, f32 bit 保存) ----
{
  const vals = [0.0, 0.25, 0.5, 0.75, 1.0, 0.123456];
  let ok = 0;
  for (const v of vals) {
    setP(eff, 3, v); setP(eff, 7, 1 - v);
    const g3 = bits2f(getP(eff, 3)), g7 = bits2f(getP(eff, 7));
    if (bits2f(f32b(v)) === g3 && bits2f(f32b(1 - v)) === g7) ok++;
  }
  ck('G3 setParameter/getParameter 往復 (6 値 × 2 param, f32 bit exact)', ok === vals.length, `${ok}/${vals.length}`);
}

// ---- G4: effGetParamName (dispatcher op8, outstr marshal) = native (op8/virt_pname) ----
{
  const eff2 = host.load(OTT_PATH, SR, 1024);
  const b = host.x.host_alloc(600);
  let ok = 0; const bad = [];
  for (let i = 0; i < 20; i++) {
    host.x.host_param_name(eff2, i, b);
    const got = host.cstr(b);
    const nat = natCStr('virt_pname', i + 1);
    if (got === nat) ok++; else bad.push(`p${i}:'${got}'≠'${nat}'`);
  }
  ck('G4 effGetParamName ×20 (lift 済み getParamName) = native と一致', ok === 20, ok === 20 ? '20/20 (p0=' + host.cstr(b) + ')' : bad.join(' ').slice(0, 140));
  host.x.host_close(eff2);
}

// ---- G5: effGetParamLabel (dispatcher op6) = native (virt_plabel) ----
{
  const eff2 = host.load(OTT_PATH, SR, 1024);
  const b = host.x.host_alloc(600);
  let ok = 0; const bad = [];
  for (let i = 0; i < 20; i++) {
    host.dv.fill ? host.dv.buffer : 0;
    bridge.icall(slotOf(eff2, 8), [BigInt(eff2), 6n, BigInt(i), 0n, BigInt(b), 0n]);
    const got = host.cstr(b);
    const nat = natCStr('virt_plabel', i + 1);
    if (got === nat) ok++; else bad.push(`p${i}:'${got}'≠'${nat}'`);
  }
  ck('G5 effGetParamLabel ×20 (2 段 jump table 経路) = native と一致', ok === 20, ok === 20 ? '20/20' : bad.join(' ').slice(0, 140));
  host.x.host_close(eff2);
}

// ---- G6: effGetParamDisplay (整数系 formatter のみ native 参照あり) ----
{
  const eff2 = host.load(OTT_PATH, SR, 1024);
  const b = host.x.host_alloc(600);
  const DISP_OK = [4, 11, 12, 13, 14, 15, 19];
  let ok = 0; const bad = [];
  for (const i of DISP_OK) {
    for (let k = 0; k < 20; k++) setP(eff2, k, 0.5);   // native (exp7) と同じ 0.5 preset 状態
    host.x.host_dispatch(eff2, 7, i, 0n, b, 0);
    const got = host.cstr(b);
    if (got.length > 0) ok++; else bad.push(`p${i} empty`);
  }
  ck('G6 effGetParamDisplay (整数系 7 param, 0.5 preset) が文字列を返す (float 系は CRT 未初期化で native 参照不能 = 到達確認)', ok === DISP_OK.length, `${ok}/${DISP_OK.length}`);
  host.x.host_close(eff2);
}

// ---- G7: chunk round-trip (op23/op24) ----
{
  const eff2 = host.load(OTT_PATH, SR, 1024);
  const data = host.x.host_alloc(64);
  for (let i = 0; i < 64; i++) host.dv.setUint8(data + i, i * 3 + 1);
  const cptrBox = host.x.host_alloc(8);
  const rSet = host.x.host_dispatch(eff2, 24, 1, 64n, data, 0);
  const rGet = host.x.host_dispatch(eff2, 23, 1, 0n, cptrBox, 0);
  const nri = (s, i) => { const v = natCall(s, i).rax; return typeof v === 'string' ? parseInt(v) : v; };
  const natSet = nri('chunk_rt', 1), natGet = nri('chunk_rt', 2);
  ck('G7 effSetChunk/effGetChunk round-trip = native と一致 (OTT は ProgramChunks 非搭載 → base 既定 0)', rSet === natSet && rGet === natGet && natGet === 0, `set=${rSet} get=${rGet} (native ${natSet}/${natGet})`);
  host.x.host_close(eff2);
}

// ---- G8: 実処理 (host.load 相当の呼出列 → processReplacing 128f) = native (h2_full) ----
{
  const eff2 = host.load(OTT_PATH, SR, 1024);
  host.x.host_dispatch(eff2, 10, 0, 0n, 0, SR);            // effSetSampleRate(44100)
  host.x.host_dispatch(eff2, 11, 0, 1024n, 0, 0);          // effSetBlockSize(1024)
  host.x.host_dispatch(eff2, 12, 0, 1n, 0, 0);             // effMainsChanged(1)
  for (let i = 0; i < 19; i++) host.x.host_set_param(eff2, i, 0.5);
  host.x.host_dispatch(eff2, 12, 0, 1n, 0, 0);             // effMainsChanged(1) (param 後)
  const au = host.mkAudio(HALF); host.fill(au);
  host.x.host_process(eff2, au.inA, au.outA, HALF);
  const got = host.outBits(au);
  const natCalls = NAT['h2_full']['calls'];
  const natHex = natCalls[natCalls.length - 2]['out'];
  const natBuf = Buffer.from(natHex, 'hex');
  const nat = Array.from(new Uint32Array(natBuf.buffer.slice(natBuf.byteOffset, natBuf.byteOffset + natBuf.length)));
  let eq = 0; for (let i = 0; i < got.length; i++) if (got[i] === nat[i]) eq++;
  const f = new Float32Array(new Uint32Array(got).buffer);
  const nz = [...f].filter((v) => v !== 0 && !Number.isNaN(v)).length;
  ck('G8 processReplacing 128f (bridge 経由) = native 実機械語と全 bit 一致・junk 0', eq === got.length && nz > 0, `${eq}/${got.length} cells (128f×2ch), nonzero ${nz}`);
  metrics.proc_cells = [eq, got.length];
  const au2 = host.mkAudio(HALF); host.fill(au2, 7);
  host.x.host_process(eff2, au2.inA, au2.outA, HALF);
  metrics.proc2_diff = host.outBits(au2).filter((v, i) => v !== got[i]).length;
  host.x.host_close(eff2);
}

// ---- G9: 2 instance 交互 128f (AudioWorklet 想定) — instance 間状態漏れ無し ----
{
  const eA = host.load(OTT_PATH, SR, 1024), eB = host.load(OTT_PATH, SR, 1024);
  for (const e of [eA, eB]) { for (let i = 0; i < 19; i++) host.x.host_set_param(e, i, 0.5); host.x.host_dispatch(e, 12, 0, 1n, 0, 0); }
  const aA = host.mkAudio(HALF), aB = host.mkAudio(HALF); host.fill(aA); host.fill(aB);
  host.x.host_process(eA, aA.inA, aA.outA, HALF);
  host.x.host_process(eB, aB.inA, aB.outA, HALF);
  const d = host.outBits(aA).filter((v, i) => v !== host.outBits(aB)[i]).length;
  ck('G9 A/B 2 instance 交互 128f の出力が一致 (module 共有・状態漏れ無し)', d === 0, `diff=${d}/1024`);
  host.x.host_close(eA); host.x.host_close(eB);
}

// ---- G10: effClose → 再ロード ----
{
  host.x.host_close(eff);
  const eff3 = host.load(OTT_PATH, SR, 1024);
  ck('G10 effClose 後の再ロードで正常動作', eff3 !== 0 && host.info().magicOk === 1);
  host.x.host_close(eff3);
}

// ---- 性能 (参考): bridge 経由 processReplacing 128f ----
{
  const e = host.load(OTT_PATH, SR, 1024);
  for (let i = 0; i < 19; i++) host.x.host_set_param(e, i, 0.5);
  host.x.host_dispatch(e, 12, 0, 1n, 0, 0);
  const au = host.mkAudio(HALF);
  const [pi, po] = [au.inA, au.outA];
  for (let i = 0; i < 300; i++) host.x.host_process(e, pi, po, HALF);
  let t = process.hrtime.bigint();
  const ITER = 3000;
  for (let i = 0; i < ITER; i++) host.x.host_process(e, pi, po, HALF);
  const us = Number(process.hrtime.bigint() - t) / 1000 / ITER;
  const budget = (HALF / SR) * 1e6;
  metrics.bridged_us_per_128f = +us.toFixed(2);
  metrics.budget_us_128f = +budget.toFixed(1);
  console.log(`INFO bridge 経由 processReplacing 128f: ${us.toFixed(1)} µs/call (RT 予算 ${budget.toFixed(0)} µs の ${(us / budget * 100).toFixed(1)}%)`);
  host.x.host_close(e);
}

metrics.bridge_stats = bridge.stats;
const broken = checks.filter((c) => !c.ok).length;
console.log(`[surrogate_harness] checks ${checks.length} / broken ${broken}`);
if (OUT) fs.writeFileSync(OUT, JSON.stringify({ checks, metrics }, null, 1));
process.exit(broken ? 1 : 0);
