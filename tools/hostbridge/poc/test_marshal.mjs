// test_marshal.mjs — bridge の marshal 規則エンジン単体試験 (OTT 非依存: JS 製 FakeGuest + 実 host_vst2.wasm).
//   OTT は MIDI/chunk/GUI 系 opcode を処理しないため、規則表の各 kind をここで網羅する.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ModuleTable, HostBridge, Space } from './hb_bridge.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const hostMod = new WebAssembly.Module(fs.readFileSync(path.join(HERE, '../work/host_vst2.wasm')));
const checks = [];
const ck = (n, c, x = '') => { checks.push(c); console.log(c ? 'OK  ' : 'FAIL', n, x); };

const FN = { DISP: 0x1000, PROC: 0x1001, SETP: 0x1002, GETP: 0x1003, PREP: 0x1004, PDBL: 0x1005 };
class FakeGuest {
  constructor() { this.mem = new Uint8Array(1 << 20); this.mod = {}; this.space = null; this.byPe = new Map(); this.entryCtx = null; this.seen = []; }
  get u8() { return this.mem; }
  get dv() { return new DataView(this.mem.buffer); }
  init() { this.space = new Space(0x10000, 0x40000); }
  entry(sym, token) {
    if (!this.mod.hbHostCall(0, 1, 0, 0, 0, 0, 0)) return 0n; // audioMasterVersion
    const d = this.dv, e = 0x1000;
    d.setInt32(e, 0x56737450, true);
    d.setBigUint64(e + 0x08, BigInt(FN.DISP), true); d.setBigUint64(e + 0x10, BigInt(FN.PROC), true);
    d.setBigUint64(e + 0x18, BigInt(FN.SETP), true); d.setBigUint64(e + 0x20, BigInt(FN.GETP), true);
    d.setInt32(e + 0x28, 3, true); d.setInt32(e + 0x2c, 5, true); d.setInt32(e + 0x30, 2, true); d.setInt32(e + 0x34, 2, true); d.setInt32(e + 0x38, 0x10 | 0x20, true);
    d.setBigUint64(e + 0x60, BigInt(e), true); d.setInt32(e + 0x70, 0x46414b45, true); d.setInt32(e + 0x74, 7, true);
    d.setBigUint64(e + 0x78, BigInt(FN.PREP), true);
    return BigInt(e);
  }
  call(fn, a) {
    a = a.map((v) => BigInt(v));
    const n = (i) => Number(BigInt.asUintN(64, a[i] ?? 0n)), d = this.dv, u = this.mem, f = Number(fn);
    if (f !== FN.DISP) return 0n;
    const op = Number(BigInt.asIntN(32, a[1])), eff = n(0), ptr = n(4), val = n(3);
    const cstr = (p) => { let s = ''; while (u[p]) s += String.fromCharCode(u[p++]); return s; };
    const put = (p, s) => { for (let i = 0; i < s.length; i++) u[p + i] = s.charCodeAt(i); u[p + s.length] = 0; };
    switch (op) {
      case 45: put(ptr, 'FakePlugin'); return 1n;
      case 51: return cstr(ptr) === 'bypass' ? 1n : BigInt.asUintN(64, -1n);
      case 13: { const r = 0x80100; d.setInt16(r, 0, true); d.setInt16(r + 2, 0, true); d.setInt16(r + 4, 240, true); d.setInt16(r + 6, 320, true); d.setBigUint64(ptr, BigInt(r), true); return 1n; }
      case 23: { const c = 0x81000; for (let i = 0; i < 3000; i++) u[c + i] = (i * 7) & 255; d.setBigUint64(ptr, BigInt(c), true); return 3000n; }
      case 24: { let s = 0; for (let i = 0; i < val; i++) s += u[ptr + i]; return BigInt(s); }
      case 25: { const nev = d.getInt32(ptr, true); let s = nev * 1000; for (let i = 0; i < nev; i++) { const ep = Number(d.getBigUint64(ptr + 0x10 + i * 8, true)); s += d.getInt32(ep + 4, true) + u[ep + 24]; } return BigInt(s); }
      case 33: u.fill(0xab, ptr, ptr + 0x80); return 1n;
      case 42: { const n1 = d.getInt32(val + 4, true), n2 = d.getInt32(ptr + 4, true); return BigInt(n1 * 100 + n2 + (u[val + 8] === 0x11 ? 7 : 0)); }
      case 14: return BigInt(ptr);
      case 99: { // plugin → host upcall 一式
        let r = 0;
        const t = this.mod.hbHostCall(eff, 7, 0, 0, 0, 0, 0);               // GetTime → guest pointer
        if (t > 0 && t < this.mem.length && d.getFloat64(t, true) === 12345 && d.getFloat64(t + 8, true) === 44100) r |= 1;
        this.mod.hbHostCall(eff, 32, 0, 0, 0, 0x82000, 0); if (cstr(0x82000) === 'Image-Line') r |= 2;   // GetVendorString (outstr)
        d.setInt32(0x82100, 2, true); d.setBigUint64(0x82110, 0x82200n, true); d.setBigUint64(0x82118, 0x82300n, true);
        d.setInt32(0x82204, 24, true); d.setInt32(0x82304, 24, true);
        if (this.mod.hbHostCall(eff, 8, 0, 0, 0, 0x82100, 0) === 21) r |= 4;                             // ProcessEvents (events_in) → host 21
        put(0x82400, 'sendVstEvents'); if (this.mod.hbHostCall(eff, 37, 0, 0, 0, 0x82400, 0) === 1) r |= 8; // CanDo (instr)
        if (this.mod.hbHostCall(eff, 3, 0, 0, 0, 0xdeadbee0, 0) === 0) r |= 16;                            // 規則無し op + ptr → host へ渡らない
        return BigInt(r);
      }
      default: return ptr !== 0 ? 0xbadn : 0n; // 規則無し opcode で ptr が見えたら 0xbad (本来 0 のはず)
    }
  }
}

const fake = new FakeGuest();
const desc = { id: 'fake.vst2', vendor: 'Fake', aliases: ['fake_x64.dll'], exports: { VSTPluginMain: 'VSTPluginMain' }, acquire: () => fake, release() {} };
const bridge = new HostBridge(new ModuleTable().register(desc));
const inst = new WebAssembly.Instance(hostMod, bridge.imports());
bridge.attachHost(inst);
const x = inst.exports;
const hu8 = () => new Uint8Array(x.memory.buffer), hdv = () => new DataView(x.memory.buffer);
const wstr = (s) => { const p = x.host_alloc(2 * (s.length + 1)); const d = hdv(); for (let i = 0; i < s.length; i++) d.setUint16(p + 2 * i, s.charCodeAt(i), true); d.setUint16(p + 2 * s.length, 0, true); return p; };
const cs = (p, m = 64) => { const u = hu8(); let s = ''; while (m-- > 0 && u[p]) s += String.fromCharCode(u[p++]); return s; };
const putc = (s) => { const p = x.host_alloc(s.length + 1); hu8().set(Buffer.from(s + '\0', 'latin1'), p); return p; };

const e = x.host_load_plugin(wstr('C:\\x\\fake_x64.dll'), 48000, 512);
ck('M0 fake plugin load (entry→upcall version→AEffect proxy)', e !== 0 && cs(x.host_info()) === 'FakePlugin', cs(x.host_info()));
ck('M0b AEffect plugin-owned 欄が proxy に反映 (numPrograms=3, numParams=5, uniqueID, version)', hdv().getInt32(e + 0x28, true) === 3 && hdv().getInt32(e + 0x2c, true) === 5 && hdv().getInt32(e + 0x70, true) === 0x46414b45 && hdv().getInt32(e + 0x74, true) === 7);

// instr / outstr
ck('M1 instr(effCanDo "bypass")=1, 他=-1', x.host_dispatch(e, 51, 0, 0n, putc('bypass'), 0) === 1 && x.host_dispatch(e, 51, 0, 0n, putc('nope'), 0) === -1);
// rectpp
{ const pp = x.host_alloc(8); hdv().setBigUint64(pp, 0n, true); const r = x.host_dispatch(e, 13, 0, 0n, pp, 0); const rp = Number(hdv().getBigUint64(pp, true)); const d = hdv();
  ck('M2 rectpp: ERect** が host 側 buffer を指し {0,0,240,320}', r === 1 && rp !== 0 && d.getInt16(rp + 4, true) === 240 && d.getInt16(rp + 6, true) === 320, `rp=0x${rp.toString(16)}`); }
// chunk_out / chunk_in
{ const pp = x.host_alloc(8); const r = x.host_dispatch(e, 23, 0, 0n, pp, 0); const cp = Number(hdv().getBigUint64(pp, true)); const u = hu8(); let ok = r === 3000 && cp !== 0;
  for (let i = 0; ok && i < 3000; i++) if (u[cp + i] !== ((i * 7) & 255)) ok = false;
  ck('M3a chunk_out: 3000B 全バイトが host 側へ複製され *ptr が host pointer', ok);
  let sum = 0; const src = x.host_alloc(500); for (let i = 0; i < 500; i++) { hu8()[src + i] = i & 255; sum += i & 255; }
  ck('M3b chunk_in: value バイトが guest へ複製', x.host_dispatch(e, 24, 0, 500n, src, 0) === sum, `sum=${sum}`); }
// events_in (host→guest)
{ const ev = x.host_alloc(0x10 + 16), d = hdv(); d.setInt32(ev, 2, true); const a = x.host_alloc(32), b = x.host_alloc(32);
  d.setInt32(a + 4, 24, true); hu8()[a + 24] = 5; d.setInt32(b + 4, 24, true); hu8()[b + 24] = 6; d.setBigUint64(ev + 0x10, BigInt(a), true); d.setBigUint64(ev + 0x18, BigInt(b), true);
  ck('M4 events_in: VstEvents deep copy (numEvents*1000 + Σ(byteSize+data))', x.host_dispatch(e, 25, 0, 0n, ev, 0) === 2 * 1000 + 24 + 5 + 24 + 6); }
// struct_out
{ const p = x.host_alloc(0x80); hu8().fill(0, p, p + 0x80); const r = x.host_dispatch(e, 33, 0, 0n, p, 0); const u = hu8(); let ok = r === 1; for (let i = 0; i < 0x80; i++) if (u[p + i] !== 0xab) ok = false;
  ck('M5 struct_out(VstPinProperties 0x80B)', ok); }
// speaker_in (value と ptr の 2 ポインタ)
{ const mk = (n) => { const p = x.host_alloc(8 + n * 112); hdv().setInt32(p, 0x11, true); hdv().setInt32(p + 4, n, true); hu8()[p + 8] = 0x11; return p; };
  ck('M6 speaker_in: value/ptr 両方の VstSpeakerArrangement を複製', x.host_dispatch(e, 42, 0, BigInt(mk(2)), mk(6), 0) === 2 * 100 + 6 + 7); }
// handle passthrough
ck('M7 handle: 不透明 HWND 値をそのまま渡す', x.host_dispatch(e, 14, 0, 0n, 0x1234, 0) === 0x1234);
// 規則無し opcode で ptr
{ const before = bridge.stats.unmarshalled; const r = x.host_dispatch(e, 9998, 0, 0n, putc('x'), 0);
  ck('M8 規則無し opcode: guest へは ptr=0 (0xbad 無し) / 計上', r === 0 && bridge.stats.unmarshalled === before + 1); }
// plugin → host upcall (ret_struct / outstr / events_in / instr / 規則無し)
{ const before = bridge.stats.unmarshalled; const r = x.host_dispatch(e, 99, 0, 0n, 0, 0);
  ck('M9 upcall 5 種 (GetTime ret_struct, GetVendorString outstr, ProcessEvents events_in, CanDo instr, 規則無し)', r === 31, `bitmask=${r} (期待 31)`);
  ck('M9b 規則無し upcall の guest ポインタは host へ渡らず計上', bridge.stats.unmarshalled === before + 1); }
x.host_close(e);
const broken = checks.filter((c) => !c).length;
console.log(`[test_marshal] checks ${checks.length} / broken ${broken}`);
process.exit(broken ? 1 : 0);
