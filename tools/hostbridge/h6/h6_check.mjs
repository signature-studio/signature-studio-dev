// h6_check.mjs — HB-H6 (G1) 検収: PNG 抽出 / 宣言的 UI モデル / effEdit* 結線 (FakeGuest + 実 host_vst2.wasm + HostBridgeG1).
//   usage: node h6_check.mjs <OTT_vst2_win64.dll> <py_scan.json>   (HOSTBRIDGE: work/host_vst2.wasm は poc/build_host.sh が作る)
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { extract } from './rsrc_extract.mjs';
import { decodePng, encodePng } from './png_lite.mjs';
import { UiModel } from './ui_model.mjs';
import { loadAssets, render } from './soft_render.mjs';
import { paintCanvas } from './canvas_renderer.mjs';
import { HostBridgeG1 } from './editor_g1.mjs';
import { ModuleTable, Space } from '../poc/hb_bridge.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const [dll, pyScan] = process.argv.slice(2);
const checks = []; const t0 = performance.now();
const ck = (n, c, x = '') => { checks.push(!!c); console.log(c ? 'OK  ' : 'FAIL', n, x); };
const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');
const manifest = JSON.parse(fs.readFileSync(path.join(HERE, 'ott.ui.json'), 'utf8'));
const fourcc = (s) => (s.charCodeAt(0) << 24) | (s.charCodeAt(1) << 16) | (s.charCodeAt(2) << 8) | s.charCodeAt(3);

// ================= R: .rsrc PNG 抽出 =================
const items = extract(dll), pngs = items.filter((i) => i.kind === 'png');
const pngBytes = pngs.reduce((a, i) => a + i.size, 0);
ck('R1 .rsrc 木から PNG 4 件 / 計 377,397 B (HOSTBRIDGE §2.6 「PNG ~377 KB」の実測)', items.length === 8 && pngs.length === 4 && pngBytes === 377397, `resources=${items.length} png=${pngs.length} bytes=${pngBytes}`);
const rsrcOf = (key) => { const [t, n] = key.split('/'); return items.find((i) => i.typeName === t && String(i.name) === n); };
const getRsrc = (key) => rsrcOf(key).data;
let hashOk = 0, dimOk = 0;
for (const a of Object.values(manifest.assets)) { const r = rsrcOf(a.rsrc); if (r.sha256 === a.sha256) hashOk++; if (r.w === a.w && r.h === a.h) dimOk++; }
ck('R2 manifest が参照する 4 資産の sha256 / 寸法が抽出物と一致', hashOk === 4 && dimOk === 4, `sha256 ${hashOk}/4 dims ${dimOk}/4`);
{ // チャンク CRC (zlib.crc32) 全検査 + デコード
  let chunks = 0, bad = 0;
  for (const p of pngs) { let q = 8; for (;;) { const n = p.data.readUInt32BE(q); const crc = zlib.crc32(p.data.subarray(q + 4, q + 8 + n)); if (crc !== p.data.readUInt32BE(q + 8 + n)) bad++; chunks++; if (p.data.toString('latin1', q + 4, q + 8) === 'IEND') break; q += 12 + n; } }
  let decoded = 0; for (const p of pngs) { const d = decodePng(p.data); if (d.w === p.w && d.h === p.h && d.rgba.length === p.w * p.h * 4) decoded++; }
  ck('R3 PNG 全 chunk の CRC 一致 + png_lite で全件デコード', bad === 0 && decoded === 4, `chunks=${chunks} crcBad=${bad} decoded=${decoded}/4`);
}
{ // 別算法 (verify_rsrc.py: 木を使わない生バイト走査) との照合
  const py = JSON.parse(fs.readFileSync(pyScan, 'utf8'));
  const a = pngs.map((p) => p.sha256).sort().join(), b = py.map((p) => p.sha256).sort().join();
  ck('R4 別算法 (python 生バイト走査 + CRC) と PNG 集合 (件数/sha256) が一致', py.length === pngs.length && a === b, `py=${py.length} node=${pngs.length}`);
}
{ // ネガティブ: bg の 1 byte を壊すと pin と不一致
  const bad = Buffer.from(getRsrc('PNG/128')); bad[1000] ^= 1;
  ck('N1 (neg) bg 1 byte 反転 → manifest の sha256 pin と不一致で検出', sha(bad) !== manifest.assets.bg.sha256 && sha(getRsrc('PNG/128')) === manifest.assets.bg.sha256);
}
const assets = loadAssets(manifest, getRsrc);

// ================= M: UiModel =================
const NAMES = ['Bypass', 'Depth', 'Time', 'In Gain', 'Out Gain', 'Clean XOV', 'Thresh L', 'Thresh M', 'Thresh H', 'Gain L', 'Gain M', 'Gain H',
  'Byp Upwd L', 'Byp Upwd M', 'Byp Upwd H', 'Byp Dnwd L', 'Byp Dnwd M', 'Byp Dnwd H', 'Upwd Strgth', 'Dnwd Strgth']; // 20 (p0=Bypass: h2 REPORT G4)
{
  const m = new UiModel(manifest, assets); const r = m.resolve(NAMES);
  ck('M1 manifest 9 control が param 名で解決 (missing 0) / 未束縛 param 11 件', r.missing.length === 0 && m.unbound.length === 11, `bound=${9 - r.missing.length} unbound=${m.unbound.length}`);
  const fr = (v) => { m.controls[0].value = v; return m.displayList().find((x) => x.asset === 'knobTick' && x.id === 'depth').frame; };
  ck('M2 フィルムストリップ frame = round(v*120): 0→0, 0.5→60, 1→120, 0.25→30', fr(0) === 0 && fr(0.5) === 60 && fr(1) === 120 && fr(0.25) === 30);
  const m2 = new UiModel({ ...manifest, controls: manifest.controls.map((c) => c.id === 'depth' ? { ...c, param: 'Depthh' } : c) }, assets);
  const r2 = m2.resolve(NAMES);
  ck('N2 (neg) manifest の param 名を 1 文字壊す → missing=["Depthh"] で検出', r2.missing.length === 1 && r2.missing[0] === 'Depthh');
}

// ================= E: effEdit* 結線 =================
const FN = { DISP: 0x1000, SETP: 0x1002, GETP: 0x1003, PREP: 0x1004, PROC: 0x1001 };
class FakeOtt { // OTT 相当の VST2 guest: 20 param (float), 名前/表示, editor 系 opcode は OTT 同様 0 返し (flags=0x18: HasEditor 無し)
  constructor() { this.mem = new Uint8Array(1 << 20); this.mod = {}; this.space = null; this.byPe = new Map(); this.entryCtx = null; this.params = new Float32Array(20); this.editorOps = []; this.log = []; }
  get u8() { return this.mem; }
  get dv() { return new DataView(this.mem.buffer); }
  init() { this.space = new Space(0x10000, 0x40000); }
  entry() {
    if (!this.mod.hbHostCall(0, 1, 0, 0, 0, 0, 0)) return 0n;
    const d = this.dv, e = 0x1000;
    d.setInt32(e, 0x56737450, true); d.setBigUint64(e + 0x08, BigInt(FN.DISP), true); d.setBigUint64(e + 0x10, BigInt(FN.PROC), true);
    d.setBigUint64(e + 0x18, BigInt(FN.SETP), true); d.setBigUint64(e + 0x20, BigInt(FN.GETP), true);
    d.setInt32(e + 0x28, 1, true); d.setInt32(e + 0x2c, 20, true); d.setInt32(e + 0x30, 2, true); d.setInt32(e + 0x34, 2, true); d.setInt32(e + 0x38, 0x18, true);
    d.setBigUint64(e + 0x60, BigInt(e), true); d.setInt32(e + 0x70, 0x58665454, true); d.setInt32(e + 0x74, 1, true); d.setBigUint64(e + 0x78, BigInt(FN.PREP), true);
    return BigInt(e);
  }
  call(fn, a) {
    a = a.map((v) => BigInt(v)); const f = Number(fn), u = this.mem, d = this.dv;
    const put = (p, s) => { for (let i = 0; i < s.length; i++) u[p + i] = s.charCodeAt(i); u[p + s.length] = 0; };
    if (f === FN.SETP) { const b = new Uint32Array([Number(BigInt.asUintN(32, a[2]))]); this.params[Number(a[1])] = new Float32Array(b.buffer)[0]; this.log.push('set'); return 0n; }
    if (f === FN.GETP) return BigInt(new Uint32Array(new Float32Array([this.params[Number(a[1])]]).buffer)[0]);
    if (f !== FN.DISP) return 0n;
    const op = Number(BigInt.asIntN(32, a[1])), idx = Number(a[2]), ptr = Number(BigInt.asUintN(64, a[4]));
    switch (op) {
      case 8: put(ptr, NAMES[idx]); return 0n;
      case 7: put(ptr, this.params[idx].toFixed(2)); return 0n;
      case 45: put(ptr, 'OTT'); return 1n;
      case 13: case 14: case 15: case 19: this.editorOps.push(op); return 0n; // editor NULL (h2 と同じ)
      default: return 0n;
    }
  }
}
const hostWasm = path.join(HERE, '../work/host_vst2.wasm');
const hostMod = new WebAssembly.Module(fs.readFileSync(hostWasm));
function boot(editors) {
  const fake = new FakeOtt();
  const desc = { id: 'xfer.ott.vst2', vendor: 'Xfer Records', aliases: ['OTT_x64.dll'], exports: { VSTPluginMain: 'VSTPluginMain' }, acquire: () => fake, release() {} };
  const bridge = new HostBridgeG1(new ModuleTable().register(desc), editors);
  const inst = new WebAssembly.Instance(hostMod, bridge.imports()); bridge.attachHost(inst);
  const x = inst.exports, hdv = () => new DataView(x.memory.buffer);
  const wp = x.host_alloc(64), w = 'C:\\x\\OTT_x64.dll'; for (let i = 0; i < w.length; i++) hdv().setUint16(wp + 2 * i, w.charCodeAt(i), true);
  const e = x.host_load_plugin(wp, 44100, 128);
  return { fake, bridge, x, e, hdv, flags: () => hdv().getInt32(x.host_info() ? e + 0x38 : 0, true) };
}
class MemSurface { constructor() { this.frames = 0; this.last = null; this.model = null; this.closed = 0; } present(list, model) { this.frames++; this.last = list; this.model = model; } close() { this.closed++; } }

const surf = new MemSurface(), hwndSeen = [];
const editors = new Map([[fourcc(manifest.plugin.uniqueID), { manifest, assets, surface: (h) => { hwndSeen.push(h); return surf; } }]]);
const B = boot(editors); const { fake, bridge, x, e } = B;
ck('E0 load (VSTPluginMain→AEffect proxy): FakeOtt の numParams=20, 素の guest flags=0x18 (HasEditor 無し)', e !== 0 && B.hdv().getInt32(e + 0x2c, true) === 20 && fake.dv.getInt32(0x1038, true) === 0x18);
ck('E1 host から見える AEffect.flags に HasEditor(bit0) が立つ (guest 側は 0x18 のまま)', (B.hdv().getInt32(e + 0x38, true) & 1) === 1 && fake.dv.getInt32(0x1038, true) === 0x18, `proxy flags=0x${B.hdv().getInt32(e + 0x38, true).toString(16)}`);

const ix = (n) => NAMES.indexOf(n);
fake.params[ix('Depth')] = Math.fround(0.25); fake.params[ix('Time')] = Math.fround(0.5);
{ const pp = x.host_alloc(8); B.hdv().setBigUint64(pp, 0n, true); const r = x.host_dispatch(e, 13, 0, 0n, pp, 0), rp = Number(B.hdv().getBigUint64(pp, true)), d = B.hdv();
  ck('E2 effEditGetRect(13): ERect={top 0,left 0,bottom 880,right 620} (manifest 矩形), 戻り 1', r === 1 && d.getInt16(rp, true) === 0 && d.getInt16(rp + 2, true) === 0 && d.getInt16(rp + 4, true) === 880 && d.getInt16(rp + 6, true) === 620); }
const rOpen = x.host_dispatch(e, 14, 0, 0n, 0x5a5a, 0);
ck('E3 effEditOpen(14, HWND=0x5a5a): 戻り 1 / surface に HWND が渡る / 初回描画 1 回', rOpen === 1 && hwndSeen.length === 1 && hwndSeen[0] === 0x5a5an && surf.frames === 1, `frames=${surf.frames}`);
{ const L = surf.last, c = (f) => L.filter(f).length;
  ck('E3b 表示リスト: bg 1 + knobBody 6 + knobTick 6 + text 6 + slider 3 (計 22)', L.length === 22 && c((i) => i.asset === 'bg') === 1 && c((i) => i.asset === 'knobBody') === 6 && c((i) => i.asset === 'knobTick') === 6 && c((i) => i.op === 'text') === 6 && c((i) => i.op === 'rect') === 3, `ops=${L.length}`);
  const t = (id) => L.find((i) => i.asset === 'knobTick' && i.id === id).frame;
  ck('E4 初期値取込: getParameter 経由 Depth=0.25→frame 30, Time=0.5→frame 60, 他 0', t('depth') === 30 && t('time') === 60 && t('ingain') === 0);
  ck('E4b readout が effGetParamDisplay 由来 ("0.25")', L.find((i) => i.op === 'text' && i.id === 'depth').text === '0.25'); }
ck('E5 editor 系 opcode は guest へ転送されない (FakeOtt の editorOps 0 件)', fake.editorOps.length === 0);

// UI 操作: Depth knob を y=205→105 へドラッグ (200px/全域 → +0.5)
const inst = [...bridge.proxy.values()][0];
{
  const amCount = (op) => { // HostInfo.am_calls は struct 内オフセット 192 + 4*12 = 240 から int32[64] (host_vst2.c の HostInfo 配置)
    return new Int32Array(x.memory.buffer, x.host_info() + 240, 64)[op]; };
  const a0 = amCount(0);
  ck('E6 down→move: pointerDown(100,205) 命中', bridge.pointer(inst, 'down', 100, 205));
  bridge.pointer(inst, 'move', 100, 105); bridge.pointer(inst, 'up');
  const want = Math.fround(0.25 + 100 / 200);
  ck('E6b plugin の setParameter が呼ばれ guest param = 0.75 (f32 bit 一致)', fake.params[ix('Depth')] === want && fake.params[ix('Depth')] === Math.fround(0.75), `guest=${fake.params[ix('Depth')]}`);
  ck('E6c host の getParameter 往復 (bridge icall) も同値', Math.fround(x.host_get_param(e, ix('Depth'))) === want);
  ck('E6d audioMasterAutomate(op 0) が host に届く (host 受信カウンタ +n = UI 変更回数)', amCount(0) - a0 === bridge.g1.automates.length && bridge.g1.automates.length > 0, `automate=${amCount(0) - a0} log=${bridge.g1.automates.length} last=${JSON.stringify(bridge.g1.automates.at(-1))}`);
  ck('E6e 描画が更新され tick frame=90 (0.75*120)', surf.last.find((i) => i.asset === 'knobTick' && i.id === 'depth').frame === 90);
  // 対称: 下へ 40px → -0.2
  bridge.pointer(inst, 'down', 100, 205); bridge.pointer(inst, 'move', 100, 245); bridge.pointer(inst, 'up');
  ck('E6f 下方向ドラッグで減少 (0.75→0.55)', Math.abs(fake.params[ix('Depth')] - 0.55) < 1e-6, `${fake.params[ix('Depth')]}`);
  // 水平スライダ
  bridge.pointer(inst, 'down', 300, 421); bridge.pointer(inst, 'up');
  ck('E7 hslider (Gain H) 絶対位置: x=300 → (300-40)/510', Math.abs(fake.params[ix('Gain H')] - (300 - 40) / 510) < 1e-6, `${fake.params[ix('Gain H')]}`);
  // 範囲外クランプ
  bridge.pointer(inst, 'down', 100, 205); bridge.pointer(inst, 'move', 100, -5000); bridge.pointer(inst, 'up');
  ck('E7b 範囲クランプ: 上限 1.0', fake.params[ix('Depth')] === 1);
}

// host 起点の変更 → effEditIdle で追従
{
  const f0 = surf.frames;
  x.host_set_param(e, ix('Time'), 0.8);
  ck('E8 host automation (setParameter) だけでは再描画しない (idle 前)', surf.frames === f0);
  x.host_dispatch(e, 19, 0, 0n, 0, 0);
  ck('E8b effEditIdle(19): getParameter を引き直して再描画 +1, Time frame=96', surf.frames === f0 + 1 && surf.last.find((i) => i.asset === 'knobTick' && i.id === 'time').frame === 96, `frames+${surf.frames - f0}`);
  x.host_dispatch(e, 19, 0, 0n, 0, 0);
  ck('E8c 変化無し idle は再描画しない', surf.frames === f0 + 1);
}

// 画素検証
{
  const W = manifest.window.width, H = manifest.window.height, model = surf.model;
  const snap = (v) => { model.controls.find((c) => c.id === 'depth').value = v; return render(model.displayList(), assets, W, H); };
  const A = snap(0), Bm = snap(1), cx = 100, cy = 205;
  let inside = 0, outside = 0;
  for (let y = 0; y < H; y++) for (let xx = 0; xx < W; xx++) { const i = (y * W + xx) * 4; const ne = A.rgba[i] !== Bm.rgba[i] || A.rgba[i + 1] !== Bm.rgba[i + 1] || A.rgba[i + 2] !== Bm.rgba[i + 2]; if (ne) { if (Math.abs(xx - cx) < 40 && Math.abs(y - cy) < 40) inside++; else outside++; } }
  ck('P1 Depth を 0→1 にすると差分画素は knob の 80×80 内のみ (内 >0 / 外 0)', inside > 0 && outside === 0, `inside=${inside} outside=${outside}`);
  // 別算法: tick frame 120 の不透明画素 (alpha=255) は合成結果と RGB が一致するはず
  const strip = assets.knobTick; let n = 0, ok = 0;
  for (let y = 0; y < 80; y++) for (let xx = 0; xx < 80; xx++) { const s = ((120 * 80 + y) * 80 + xx) * 4; if (strip.rgba[s + 3] === 255) { n++; const d = ((cy - 40 + y) * W + (cx - 40 + xx)) * 4; if (Bm.rgba[d] === strip.rgba[s] && Bm.rgba[d + 1] === strip.rgba[s + 1] && Bm.rgba[d + 2] === strip.rgba[s + 2]) ok++; } }
  ck('P2 別算法: tick 最終 frame の不透明画素が出力 RGBA と RGB 一致', n > 0 && ok === n, `opaque=${n} match=${ok}`);
  const work = path.join(HERE, 'work'); fs.mkdirSync(work, { recursive: true });
  fs.writeFileSync(path.join(work, 'editor_snapshot.png'), encodePng(render(surf.last, assets, W, H)));
  ck('P3 snapshot (work/editor_snapshot.png) 出力: 620×880', true, `sha256=${sha(fs.readFileSync(path.join(work, 'editor_snapshot.png'))).slice(0, 12)}`);
}

// Canvas renderer (mock ctx)
{
  const calls = []; const ctx = { canvas: { width: 620, height: 880 }, clearRect() { calls.push('clear'); }, drawImage(...a) { calls.push(['img', a[1], a[2]]); }, fillText() { calls.push('text'); }, fillRect() { calls.push('rect'); } };
  const L = surf.last, n = paintCanvas(ctx, L, { bg: 1, knobTick: 2, knobBody: 3, knobRing: 4 });
  const imgs = calls.filter((c) => Array.isArray(c)), ticks = imgs.filter((c) => c[2] % 80 === 0 && c[2] > 0).length;
  ck('C1 Canvas2D 描画: 表示リスト 22 op → drawImage 13 / fillText 6 / fillRect 3 (mock ctx; 実ブラウザは未検証)', n === 22 && imgs.length === 13 && calls.filter((c) => c === 'text').length === 6 && calls.filter((c) => c === 'rect').length === 3 && ticks > 0, `n=${n} drawImage=${imgs.length}`);
}

// close / 再 open / 未登録 plugin
{
  const f0 = surf.frames;
  x.host_dispatch(e, 15, 0, 0n, 0, 0); x.host_dispatch(e, 19, 0, 0n, 0, 0);
  ck('E9 effEditClose(15): surface.close() / 以後 idle は描画しない', surf.closed === 1 && surf.frames === f0 && bridge.g1.closes === 1);
  ck('E9b 再 open 可能 (戻り 1, 描画 +1)', x.host_dispatch(e, 14, 0, 0n, 0x5a5a, 0) === 1 && surf.frames === f0 + 1);
  ck('E9c 二重 open は 0 (VST2 慣習: 既に開いている)', x.host_dispatch(e, 14, 0, 0n, 0x5a5a, 0) === 0);
  ck('E10 非 editor opcode は従来経路で guest へ転送 (effGetEffectName=OTT)', (() => { const p = x.host_alloc(64); x.host_dispatch(e, 45, 0, 0n, p, 0); return new TextDecoder().decode(new Uint8Array(x.memory.buffer, p, 3)) === 'OTT'; })());
}
{ // 未登録 plugin: HasEditor を立てず, op 13/14 は従来どおり guest へ (OTT 同様 0)
  const B2 = boot(new Map()); const pp = B2.x.host_alloc(8);
  const r13 = B2.x.host_dispatch(B2.e, 13, 0, 0n, pp, 0), r14 = B2.x.host_dispatch(B2.e, 14, 0, 0n, 0x1, 0);
  ck('E11 editor 未登録 plugin: HasEditor 立たず, op 13/14 は guest 転送 (0 返し, G0 互換)', (B2.hdv().getInt32(B2.e + 0x38, true) & 1) === 0 && r13 === 0 && r14 === 0 && B2.fake.editorOps.join() === '13,14', `flags=0x${B2.hdv().getInt32(B2.e + 0x38, true).toString(16)} guestOps=${B2.fake.editorOps}`);
}
{ // ネガティブ: manifest の param 名破損 → effEditOpen=0 (editor を開かない)
  const bad = { ...manifest, controls: manifest.controls.map((c) => c.id === 'time' ? { ...c, param: 'Tiem' } : c) };
  const B3 = boot(new Map([[fourcc('XfTT'), { manifest: bad, assets, surface: () => new MemSurface() }]]));
  const r = B3.x.host_dispatch(B3.e, 14, 0, 0n, 0x1, 0);
  ck('N3 (neg) manifest param 名破損 → effEditOpen=0 / missing=["Tiem"]', r === 0 && B3.bridge.g1.lastMissing && B3.bridge.g1.lastMissing[0] === 'Tiem' && B3.bridge.g1.opens === 0);
}
const broken = checks.filter((c) => !c).length;
console.log(`[h6_check] checks ${checks.length} / broken ${broken} / ${Math.round(performance.now() - t0)} ms`);
process.exit(broken ? 1 : 0);
