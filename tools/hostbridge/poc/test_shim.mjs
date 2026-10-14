// test_shim.mjs — Win32 shim 表 (SafeLoadLibrary / GetProcAddress / SetErrorMode / FreeLibrary / timeGetTime) と
//   CreateProcessW fail-fast・bridged 無効化の単体試験 + ネガコン (実装を外すと FAIL することの確認).
//   OTT 非依存: host は実 host_vst2 を使わず WebAssembly.Memory だけを持つ偽 instance、guest は偽 descriptor.
//   node tools/hostbridge/poc/test_shim.mjs
import { ModuleTable, HostBridge, SEM_NOOPENFILEERRORBOX, THUNK_BASE, HMODULE_BASE } from './hb_bridge.mjs';

const PATH = 'C:\\Program Files\\Common Files\\VST2\\Xfer Records\\OTT_x64.dll';
const MISSING = 'C:\\nope\\missing.dll';

function makeHost() {
  const memory = new WebAssembly.Memory({ initial: 4 });
  let next = 0x1000;
  return { exports: { memory, host_alloc: (n) => { const p = next; next += (n + 15) & ~15; return p; } } };
}
const putWStr = (host, s, p) => { const d = new DataView(host.exports.memory.buffer); for (let i = 0; i < s.length; i++) d.setUint16(p + 2 * i, s.charCodeAt(i), true); d.setUint16(p + 2 * s.length, 0, true); return p; };
const putCStr = (host, s, p) => { const u = new Uint8Array(host.exports.memory.buffer); for (let i = 0; i < s.length; i++) u[p + i] = s.charCodeAt(i); u[p + s.length] = 0; return p; };
function fakeDesc(id, aliases, exports) {
  const d = { id, aliases, vendor: 'Xfer Records', exports, released: 0,
    acquire: () => ({ mod: {}, init() {}, byPe: new Map(), entryCtx: null }),
    release() { d.released++; } };
  return d;
}

// 試験ごとに新しい table / bridge を作る. TableCls / BridgeCls で mutant を差し込める.
function setup({ BridgeCls = HostBridge, TableCls = ModuleTable, clock } = {}) {
  const table = new TableCls().register(fakeDesc('xfer.ott.vst2', ['OTT_x64.dll'], { VSTPluginMain: 'VSTPluginMain' }));
  const host = makeHost();
  const b = new BridgeCls(table, { clock: clock || (() => 1000) });
  b.attachHost(host);
  return { b, host, table };
}

// 全試験. 失敗件数を返す (quiet=true で出力を抑える)
function runSuite(opts = {}, quiet = false) {
  let fails = 0;
  const check = (n, c, x = '') => { if (!c) fails++; if (!quiet) console.log(c ? 'OK  ' : 'FAIL', n, x); };

  // S1 SafeLoadLibrary: LoadLibraryW は SEM_NOOPENFILEERRORBOX 下で呼ばれ、戻り後 (成功/失敗とも) に旧モードへ戻る
  {
    const { b, host } = setup(opts);
    const h = b.SafeLoadLibrary(putWStr(host, PATH, 0x100), SEM_NOOPENFILEERRORBOX);
    check('S1a SafeLoadLibrary が成功でハンドルを返す', h !== 0n, `h=0x${BigInt(h).toString(16)}`);
    check('S1b LoadLibraryW 実行中の ErrorMode = SEM_NOOPENFILEERRORBOX', b.lastLoadMode === SEM_NOOPENFILEERRORBOX, `mode=0x${b.lastLoadMode.toString(16)}`);
    check('S1c 戻り後に ErrorMode が旧値 (0) へ戻る', b.errorMode === 0, `mode=0x${b.errorMode.toString(16)}`);
    const { b: b2, host: h2 } = setup(opts);
    const r2 = b2.SafeLoadLibrary(putWStr(h2, MISSING, 0x100), SEM_NOOPENFILEERRORBOX);
    check('S1d 未登録パスは NULL + ERROR_MOD_NOT_FOUND(126)', r2 === 0n && b2.lastError === 126, `ret=${r2} err=${b2.lastError}`);
    check('S1e 失敗時も ErrorMode は旧値へ戻る', b2.errorMode === 0, `mode=${b2.errorMode}`);
  }

  // S2 SetErrorMode は旧値を返す
  {
    const { b } = setup(opts);
    const o1 = b.SetErrorMode(0x8001), o2 = b.SetErrorMode(0);
    check('S2 SetErrorMode が旧値を返す', o1 === 0 && o2 === 0x8001, `old1=${o1} old2=0x${o2.toString(16)}`);
  }

  // S3 GetProcAddress: 大文字小文字を区別 / 未知名は NULL + 127 / 既知名は thunk VA
  {
    const { b, host } = setup(opts);
    const h = b.SafeLoadLibrary(putWStr(host, PATH, 0x100), SEM_NOOPENFILEERRORBOX);
    const ok = b.GetProcAddress(h, putCStr(host, 'VSTPluginMain', 0x400));
    const lo = b.GetProcAddress(h, putCStr(host, 'vstpluginmain', 0x440));
    const unk = b.GetProcAddress(h, putCStr(host, 'NoSuchExport', 0x480));
    check('S3a GetProcAddress 既知名は thunk VA (THUNK_BASE 以上)', ok >= THUNK_BASE, `va=0x${BigInt(ok).toString(16)}`);
    check('S3b GetProcAddress は case-sensitive (小文字は NULL)', lo === 0n, `va=0x${BigInt(lo).toString(16)}`);
    check('S3c 未知名は NULL + ERROR_PROC_NOT_FOUND(127)', unk === 0n && b.lastError === 127, `err=${b.lastError}`);
  }

  // S4 FreeLibrary: refcount 2 → 1 回目は解放しない / 2 回目で release
  {
    const { b, host, table } = setup(opts);
    const desc = table.resolve(PATH);
    const h = b.SafeLoadLibrary(putWStr(host, PATH, 0x100), SEM_NOOPENFILEERRORBOX);
    const h2 = b.SafeLoadLibrary(putWStr(host, PATH, 0x100), SEM_NOOPENFILEERRORBOX);
    check('S4a 同一 module の 2 回ロードは同一 HMODULE', h === h2 && desc.released === 0, `h=${h} h2=${h2}`);
    b.FreeLibrary(h);
    check('S4b refcount>0 では release しない', desc.released === 0, `released=${desc.released}`);
    b.FreeLibrary(h);
    check('S4c refcount 0 で release (instance 破棄)', desc.released === 1, `released=${desc.released}`);
  }

  // S5 timeGetTime: 起動からの経過 ms / DWORD 折返し
  {
    let now = 5000;
    const { b } = setup({ ...opts, clock: () => now });
    const t0 = b.timeGetTime();
    now += 250;
    const t1 = b.timeGetTime();
    check('S5a timeGetTime は起動からの経過 ms を返す', t0 === 0 && t1 === 250, `t0=${t0} t1=${t1}`);
    now = 5000 + 0x1_0000_0000 + 7;
    const t2 = b.timeGetTime();
    check('S5b timeGetTime は DWORD (32bit) に折返す', t2 === 7, `t2=${t2}`);
  }

  // S6 CreateProcessW: 呼ばれたら原因付きで fail-fast (黙って成功しない)
  {
    const { b } = setup(opts);
    let thrown = null;
    try { b.imports().hb.CreateProcessW(); } catch (e) { thrown = e; }
    check('S6a CreateProcessW は throw (fail-fast)', thrown instanceof Error, thrown ? thrown.message.slice(0, 60) : 'no throw');
    check('S6b 例外メッセージに bridged と HOSTBRIDGE §1.6 を含む', !!thrown && /bridged/.test(thrown.message) && /HOSTBRIDGE §1\.6/.test(thrown.message));
  }

  // S7 bridged 無効化: 登録時に bridge 種別を 0 へ強制し、要求値は保持する
  {
    const t = new (opts.TableCls || ModuleTable)().register({ id: 'y', aliases: ['y.dll'], vendor: 'v', exports: {}, acquire() {}, release() {}, bridge: 3 });
    const d = t.byId.get('y');
    check('S7a bridged 要求 (3) が native (0) へ強制される', d.bridge === 0 && d.bridgeRequested === 3, `bridge=${d.bridge} req=${d.bridgeRequested}`);
  }

  // S8 既存経路 (LoadLibraryW→GetProcAddress) は不変
  {
    const { b, host } = setup(opts);
    const h = b.LoadLibraryW(putWStr(host, PATH, 0x100));
    const va = b.GetProcAddress(h, putCStr(host, 'VSTPluginMain', 0x400));
    check('S8 LoadLibraryW→GetProcAddress の既存 OTT 経路は従来どおり', h !== 0n && va >= THUNK_BASE && b.errorMode === 0);
  }

  // S9 HMODULE 一意性 (#2520): 解放で loaded.size が減っても、再ロードや別 module のロードで生存中の handle と衝突しない
  {
    const { b, host, table } = setup(opts);
    const names = ['A_x64.dll', 'B_x64.dll', 'C_x64.dll'];
    names.forEach((n, i) => table.register(fakeDesc(`xfer.${'abc'[i]}.vst2`, [n], { VSTPluginMain: 'VSTPluginMain' })));
    const ld = (n) => b.LoadLibraryW(putWStr(host, n, 0x100));
    const hA = ld(names[0]), hB = ld(names[1]), hC = ld(names[2]);
    b.FreeLibrary(hA);
    const hA2 = ld(names[0]);
    check('S9a 解放後の再ロードが生存中の別 module と同じ HMODULE を返さない', hA2 !== hB && hA2 !== hC && b.byHandle.size === b.loaded.size, `hB=0x${hB.toString(16)} hC=0x${hC.toString(16)} hA2=0x${hA2.toString(16)} byHandle=${b.byHandle.size} loaded=${b.loaded.size}`);
    let clash = 0;
    for (let i = 0; i < 9; i++) {
      const lm = [...b.loaded.values()][i % b.loaded.size];
      b.FreeLibrary(lm.handle);
      ld(lm.desc.aliases[0]);
      if (b.byHandle.size !== b.loaded.size) clash++;
    }
    check('S9b ロード→解放→再ロードを 9 回繰り返しても生存 handle は相異なる', clash === 0, `clash=${clash}`);
  }
  return fails;
}

// ---- 本物の実装 ----
const realFails = runSuite({}, false);
console.log(realFails === 0 ? '[shim] real: ALL PASS' : `[shim] real: ${realFails} FAIL`);

// ---- ネガコン: 各実装を外した mutant で、対応する試験が FAIL することを確認 ----
class NoRestoreMode extends HostBridge { SafeLoadLibrary(p, m) { this.SetErrorMode(m); return this.LoadLibraryW(p); } }
class CaseInsensitive extends HostBridge { readCStr(u8, p, max) { return super.readCStr(u8, p, max).toLowerCase(); } }
class NoRefcount extends HostBridge { FreeLibrary(h) { return super.FreeLibrary(h) && 0 || 1; } }
class ReleaseAtOnce extends HostBridge { FreeLibrary(h) { const lm = this.byHandle.get(BigInt.asUintN(64, BigInt(h))); if (lm) lm.refs = 1; return super.FreeLibrary(h); } }
class ConstClock extends HostBridge { timeGetTime() { return 0; } }
class SizeHandle extends HostBridge { allocHandle() { return HMODULE_BASE + BigInt(this.loaded.size + 1) * 0x10000n; } }
class SilentCreateProcess extends HostBridge { CreateProcessW() { return 1; } }
class NoBridgeDisable extends ModuleTable { register(desc) { this.byId.set(desc.id, desc); for (const a of desc.aliases) this.alias.set(a.toLowerCase(), desc); this.alias.set(desc.id.toLowerCase(), desc); return this; } }
const mutants = [
  ['SafeLoadLibrary がモードを戻さない', { BridgeCls: NoRestoreMode }],
  ['GetProcAddress が大文字小文字を無視', { BridgeCls: CaseInsensitive }],
  ['FreeLibrary が refcount を無視 (常に解放)', { BridgeCls: ReleaseAtOnce }],
  ['timeGetTime が定数 0', { BridgeCls: ConstClock }],
  ['HMODULE 採番を loaded.size 基準に戻す (解放後に衝突)', { BridgeCls: SizeHandle }],
  ['CreateProcessW が黙って成功', { BridgeCls: SilentCreateProcess }],
  ['bridged 強制無効化を外す (register 素通し)', { TableCls: NoBridgeDisable }],
];
let negCaught = 0;
for (const [name, opts] of mutants) {
  const f = runSuite(opts, true);
  if (f > 0) negCaught++;
  console.log(f > 0 ? 'OK  ' : 'FAIL', `ネガコン [${name}] → ${f} FAIL (期待: FAIL)`);
}
console.log(`[shim] negative controls caught ${negCaught}/${mutants.length}`);
const ok = realFails === 0 && negCaught === mutants.length;
console.log(ok ? '[shim] ALL PASS' : '[shim] FAIL');
process.exit(ok ? 0 : 1);
