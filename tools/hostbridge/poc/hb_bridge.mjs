// hb_bridge.mjs — hostbridge: 「事前登録 wasm モジュール表」+ LoadLibrary/GetProcAddress shim + VST2 境界 marshaller.
//
// 設計 (HOSTBRIDGE.md §2):
//   * ホスト (FL 側 = lift 済み x64 コード / PoC では host_vst2.wasm) と各プラグインは **別 wasm instance・別 linear memory**.
//   * ホストが見る関数ポインタは全て本 bridge が払い出す合成 VA ("thunk slot"); 呼出は icall() に集約される
//     (lift 済みコードの間接呼出が最終的に落ちる 1 点).
//   * VST2 境界 (AEffect / dispatcher / process / audioMaster) は table 駆動で marshalling する.
//   * guest ABI 契約: exports {hb_plugin_init, hb_scratch, VSTPluginMain, hb_icall}, import {hb_host_call}.

export const THUNK_BASE = 0x00007ff700000000n; // 合成関数ポインタ VA
export const THUNK_STRIDE = 0x10n;
export const HMODULE_BASE = 0x00007ff6a0000000n; // 合成 HMODULE
const ERROR_MOD_NOT_FOUND = 126, ERROR_PROC_NOT_FOUND = 127, ERROR_NOT_SUPPORTED = 50;
export const SEM_NOOPENFILEERRORBOX = 0x8000; // Wrapper の SafeLoadLibrary が使うエラーモード (fw:0x449770)
// bridged 経路の強制無効化: Wrapper の this+0x761 (0=native, 2=32bit bridge, 3=64bit bridge; HOSTBRIDGE §1.6)
export const forceNative = (desc) => { desc.bridgeRequested = desc.bridge ?? 0; desc.bridge = 0; return desc; };

// ---- AEffect (Win64 配置) ----
const AE = { magic: 0, dispatcher: 0x08, process: 0x10, setParameter: 0x18, getParameter: 0x20, numPrograms: 0x28,
  numParams: 0x2c, numInputs: 0x30, numOutputs: 0x34, flags: 0x38, resvd1: 0x40, resvd2: 0x48, initialDelay: 0x50,
  ioRatio: 0x5c, object: 0x60, user: 0x68, uniqueID: 0x70, version: 0x74, processReplacing: 0x78,
  processDoubleReplacing: 0x80, SIZE: 0xc0 };
const AE_FN_FIELDS = ['dispatcher', 'process', 'setParameter', 'getParameter', 'processReplacing', 'processDoubleReplacing'];
// host が書く欄 / plugin が書く欄 (mirror protocol)
const AE_HOST_OWNED = [[0x40, 0x10], [0x68, 0x08], [0x70, 0x04]]; // resvd1/resvd2, user, uniqueID(shell override)
const AE_PLUGIN_OWNED = [[0x28, 0x18], [0x50, 0x18], [0x60, 0x08], [0x70, 0x08]]; // numPrograms..flags, initialDelay..ioRatio, object, uniqueID/version

// ---- dispatcher の marshal 規則 (host→plugin). 根拠: Fruity Wrapper が発行する opcode 一覧 (HOSTBRIDGE.md §1.3) + 公開仕様 ----
const OUTSTR = { k: 'outstr', n: 513 }; // FL の文字列 buffer は 0x201
export const DISPATCH_RULES = {
  4: { k: 'instr' }, 5: OUTSTR, 6: OUTSTR, 7: OUTSTR, 8: OUTSTR, 13: { k: 'rectpp' }, 14: { k: 'handle' },
  23: { k: 'chunk_out' }, 24: { k: 'chunk_in' }, 25: { k: 'events_in' }, 27: { k: 'instr' }, 29: OUTSTR,
  33: { k: 'struct_out', size: 0x80 }, 34: { k: 'struct_out', size: 0x80 }, 42: { k: 'speaker_in' },
  45: OUTSTR, 46: OUTSTR, 47: OUTSTR, 48: OUTSTR, 51: { k: 'instr' }, 56: { k: 'struct_out', size: 152 },
};
// ---- audioMaster の marshal 規則 (plugin→host) ----
export const AM_RULES = {
  7: { k: 'ret_struct', size: 0x58 }, // VstTimeInfo* を返す
  8: { k: 'events_in' }, 32: { k: 'outstr', n: 64 }, 33: { k: 'outstr', n: 64 }, 37: { k: 'instr' },
};

const s64 = (x) => BigInt.asIntN(64, BigInt(x));
const u64 = (x) => BigInt.asUintN(64, BigInt(x));

export class Space { // stack discipline の bump allocator (scratch)
  constructor(base, size) { this.base = base; this.end = base + size; this.sp = base; }
  alloc(n) { n = (n + 15) & ~15; if (this.sp + n > this.end) throw new Error('hostbridge: scratch overflow'); const p = this.sp; this.sp += n; return p; }
  mark() { return this.sp; }
  release(m) { this.sp = m; }
}

// emscripten module を guest として包む
export class EmscriptenGuest {
  constructor(mod, scratchSize = 0x100000) {
    this.mod = mod; this.scratchSize = scratchSize;
    this.space = null; this.byPe = new Map(); this.entryCtx = null;
  }
  get u8() { return this.mod.HEAPU8; }
  get dv() { const u = this.mod.HEAPU8; return new DataView(u.buffer, u.byteOffset, u.length); }
  init() { this.mod._hb_plugin_init(); this.space = new Space(this.mod._hb_scratch(), this.scratchSize); }
  call(fn, a = []) {
    const g = [0n, 0n, 0n, 0n, 0n, 0n]; for (let i = 0; i < a.length; i++) g[i] = s64(a[i]);
    return BigInt.asIntN(64, this.mod._hb_icall(s64(fn), ...g));
  }
  entry(sym, audioMasterToken) {
    if (sym !== 'VSTPluginMain') throw new Error('hostbridge: unknown entry ' + sym);
    return BigInt.asIntN(64, this.mod._VSTPluginMain(s64(audioMasterToken)));
  }
}

export class ModuleTable {
  constructor() { this.byId = new Map(); this.alias = new Map(); }
  register(desc) {
    forceNative(desc);
    this.byId.set(desc.id, desc);
    for (const a of desc.aliases) this.alias.set(a.toLowerCase(), desc);
    this.alias.set(desc.id.toLowerCase(), desc);
    return this;
  }
  resolve(path) {
    const p = String(path).replace(/\\/g, '/');
    const base = p.slice(p.lastIndexOf('/') + 1).toLowerCase();
    return this.alias.get(base) || this.alias.get(p.toLowerCase()) || null;
  }
  virtualPaths() { // Plugin Manager 走査 (FindFirstFile 相当) が見る仮想 VST フォルダ
    return [...this.byId.values()].map((d) => ({ desc: d, path: `C:\\Program Files\\Common Files\\VST2\\${d.vendor}\\${d.aliases[0]}` }));
  }
}

export class HostBridge {
  constructor(table, opts = {}) {
    this.table = table; this.slots = []; this.loaded = new Map(); this.byHandle = new Map(); this.hseq = 0;
    this.proxy = new Map(); this.lastError = 0; this.depth = 0;
    this.errorMode = 0; this.lastLoadMode = 0; this.clock = opts.clock || (() => Date.now()); this.t0 = this.clock();
    this.stats = { icalls: 0, entryCalls: 0, dispatch: 0, process: 0, upcalls: 0, unmarshalled: 0, bytesIn: 0, bytesOut: 0, dispatchByOp: {}, upcallByOp: {} };
    this.host = null; this.hostScratch = null; this.trace = null;
  }
  // ---- host 側 ----
  attachHost(instance) {
    this.host = instance; this.hexp = instance.exports;
    const base = this.hexp.host_alloc(0x80000);
    this.hostScratch = new Space(base, 0x80000);
  }
  get hu8() { return new Uint8Array(this.hexp.memory.buffer); }
  get hdv() { return new DataView(this.hexp.memory.buffer); }
  imports() {
    return { hb: {
      LoadLibraryW: (p) => this.LoadLibraryW(p),
      GetProcAddress: (h, n) => this.GetProcAddress(h, n),
      FreeLibrary: (h) => this.FreeLibrary(h),
      SafeLoadLibrary: (p, mode) => this.SafeLoadLibrary(p, mode),
      SetErrorMode: (mode) => this.SetErrorMode(mode),
      timeGetTime: () => this.timeGetTime(),
      CreateProcessW: () => this.CreateProcessW(),
      icall: (fn, a0, a1, a2, a3, a4, a5) => this.icall(fn, [a0, a1, a2, a3, a4, a5]),
    } };
  }
  readWStr(p) { const d = this.hdv; let s = ''; for (;;) { const c = d.getUint16(p, true); if (!c) break; s += String.fromCharCode(c); p += 2; } return s; }
  readCStr(u8, p, max = 4096) { let s = ''; while (max-- > 0 && u8[p]) s += String.fromCharCode(u8[p++]); return s; }

  newSlot(info) { this.slots.push(info); return THUNK_BASE + BigInt(this.slots.length - 1) * THUNK_STRIDE; }
  slotOf(va) {
    const v = u64(va);
    if (v < THUNK_BASE) return null;
    const off = v - THUNK_BASE;
    if (off % THUNK_STRIDE) return null;
    return this.slots[Number(off / THUNK_STRIDE)] || null;
  }

  // ---- Win32 shim ----
  SetErrorMode(mode) { const old = this.errorMode; this.errorMode = mode >>> 0; return old; }
  // fw:0x449770 = SetErrorMode(mode) + LoadLibraryW + SetErrorMode(old). 戻り値前に必ず旧モードへ戻す.
  SafeLoadLibrary(pPath, mode) {
    const old = this.SetErrorMode(mode);
    try { return this.LoadLibraryW(pPath); } finally { this.SetErrorMode(old); }
  }
  timeGetTime() { return (this.clock() - this.t0) >>> 0; } // DWORD (ms, 32bit 折返し)
  // bridged 経路 (ilbridge.exe 起動) は wasm で無効 (HOSTBRIDGE §1.6). 呼ばれたら原因付きで即失敗する.
  CreateProcessW() {
    this.lastError = ERROR_NOT_SUPPORTED;
    throw new Error('hostbridge: CreateProcessW called — bridged plugin (ilbridge.exe) is disabled in the wasm build (HOSTBRIDGE §1.6); plugin must run as native instance');
  }
  LoadLibraryW(pPath) {
    const path = this.readWStr(pPath);
    const desc = this.table.resolve(path);
    this.lastLoadMode = this.errorMode;
    if (!desc) { this.lastError = ERROR_MOD_NOT_FOUND; if (this.trace) this.trace(`LoadLibraryW("${path}") -> NULL (126)`); return 0n; }
    let lm = this.loaded.get(desc.id);
    if (lm) lm.refs++;
    else {
      const guest = desc.acquire(); // 事前 prewarm 済み instance (sync 取得)
      guest.mod.hbHostCall = (eff, op, idx, vlo, vhi, ptr, opt) => this.upcall(guest, eff, op, idx, vlo, vhi, ptr, opt);
      guest.init();
      lm = { desc, guest, refs: 1, handle: this.allocHandle(), entrySlots: new Map() };
      this.loaded.set(desc.id, lm); this.byHandle.set(lm.handle, lm);
    }
    if (this.trace) this.trace(`LoadLibraryW("${path}") -> ${desc.id} hmodule=0x${lm.handle.toString(16)} refs=${lm.refs}`);
    return lm.handle;
  }
  allocHandle() { // 単調増加. loaded.size 基準だと解放後に生存中の handle と衝突する (#2520)
    return HMODULE_BASE + BigInt(++this.hseq) * 0x10000n;
  }
  GetProcAddress(h, pName) {
    const lm = this.byHandle.get(u64(h));
    const name = this.readCStr(this.hu8, pName);
    const sym = lm && lm.desc.exports[name]; // PE export 表同様 case-sensitive
    if (!sym) { this.lastError = ERROR_PROC_NOT_FOUND; return 0n; }
    if (!lm.entrySlots.has(name)) lm.entrySlots.set(name, this.newSlot({ kind: 'entry', lm, sym }));
    return lm.entrySlots.get(name);
  }
  FreeLibrary(h) {
    const lm = this.byHandle.get(u64(h));
    if (!lm) return 0;
    if (--lm.refs > 0) return 1;
    this.loaded.delete(lm.desc.id); this.byHandle.delete(lm.handle);
    lm.desc.release(lm.guest); // instance を破棄 (memory は GC で回収)
    for (const [pe, inst] of lm.guest.byPe) this.proxy.delete(inst.proxy);
    for (let i = 0; i < this.slots.length; i++) if (this.slots[i] && (this.slots[i].lm === lm || (this.slots[i].inst && this.slots[i].inst.lm === lm))) this.slots[i] = null;
    return 1;
  }

  // ---- 間接呼出 (guest 関数ポインタ) ----
  icall(fn, a) {
    this.stats.icalls++;
    const slot = this.slotOf(fn);
    if (!slot) throw new Error(`hostbridge: invalid guest function pointer 0x${u64(fn).toString(16)}`);
    return slot.kind === 'entry' ? this.callEntry(slot, a) : this.callAEffect(slot, a);
  }

  callEntry(slot, a) {
    this.stats.entryCalls++;
    const { lm } = slot, g = lm.guest;
    const hostCbIdx = Number(u64(a[0]));
    g.entryCtx = { hostCbIdx };
    const m = g.space.mark();
    let pe;
    try { pe = g.entry(slot.sym, 0x2000n + BigInt(hostCbIdx)); } finally { g.space.release(m); g.entryCtx = null; }
    if (pe === 0n) return 0n;
    const peN = Number(pe);
    const proxy = this.hexp.host_alloc(AE.SIZE);
    this.hu8.set(g.u8.subarray(peN, peN + AE.SIZE), proxy);
    const inst = { lm, guest: g, pe: peN, proxy, hostCbIdx, rect: 0, chunk: 0, chunkCap: 0, fnVA: {} };
    for (const f of AE_FN_FIELDS) {
      const pfn = g.dv.getBigUint64(peN + AE[f], true);
      if (pfn === 0n) continue;
      inst.fnVA[f] = this.newSlot({ kind: 'aeffect', inst, field: f, pfn });
      this.hdv.setBigUint64(proxy + AE[f], inst.fnVA[f], true);
    }
    g.byPe.set(peN, inst); this.proxy.set(proxy, inst);
    return BigInt(proxy);
  }

  syncIn(inst) {
    const h = this.hu8, g = inst.guest.u8;
    for (const [o, n] of AE_HOST_OWNED) g.set(h.subarray(inst.proxy + o, inst.proxy + o + n), inst.pe + o);
  }
  syncOut(inst) {
    const h = this.hu8, g = inst.guest.u8;
    for (const [o, n] of AE_PLUGIN_OWNED) h.set(g.subarray(inst.pe + o, inst.pe + o + n), inst.proxy + o);
  }

  callAEffect(slot, a) {
    const inst = slot.inst, g = inst.guest, pe = BigInt(inst.pe);
    if (this.proxy.get(Number(u64(a[0]))) !== inst) throw new Error('hostbridge: AEffect* does not match slot owner');
    this.syncIn(inst);
    const gm = g.space.mark(), hm = this.hostScratch.mark();
    this.depth++;
    try {
      switch (slot.field) {
        case 'dispatcher': return this.doDispatch(inst, slot.pfn, a);
        case 'setParameter': g.call(slot.pfn, [pe, a[1], a[2]]); return 0n;
        case 'getParameter': return g.call(slot.pfn, [pe, a[1]]);
        case 'processReplacing': return this.doProcess(inst, slot.pfn, a);
        default: throw new Error(`hostbridge: unsupported AEffect callback ${slot.field}`);
      }
    } finally { this.depth--; g.space.release(gm); this.hostScratch.release(hm); this.syncOut(inst); }
  }

  doProcess(inst, pfn, a) {
    this.stats.process++;
    const g = inst.guest, h = this.hu8, hd = this.hdv;
    const n = Number(BigInt.asIntN(32, a[3]));
    const inArr = Number(u64(a[1])), outArr = Number(u64(a[2]));
    const nin = hd.getInt32(inst.proxy + AE.numInputs, true), nout = hd.getInt32(inst.proxy + AE.numOutputs, true);
    const bytes = n * 4;
    const gin = g.space.alloc(nin * 8), gout = g.space.alloc(nout * 8);
    const gdv = g.dv, gu8 = g.u8;
    for (let c = 0; c < nin; c++) {
      const hp = Number(hd.getBigUint64(inArr + c * 8, true)), gp = g.space.alloc(bytes);
      gu8.set(h.subarray(hp, hp + bytes), gp); gdv.setBigUint64(gin + c * 8, BigInt(gp), true);
    }
    for (let c = 0; c < nout; c++) { const gp = g.space.alloc(bytes); gu8.fill(0, gp, gp + bytes); gdv.setBigUint64(gout + c * 8, BigInt(gp), true); }
    g.call(pfn, [inst.pe, gin, gout, n]);
    for (let c = 0; c < nout; c++) {
      const hp = Number(hd.getBigUint64(outArr + c * 8, true)), gp = Number(gdv.getBigUint64(gout + c * 8, true));
      h.set(gu8.subarray(gp, gp + bytes), hp);
    }
    this.stats.bytesIn += nin * bytes; this.stats.bytesOut += nout * bytes;
    return 0n;
  }

  doDispatch(inst, pfn, a) {
    this.stats.dispatch++;
    const op = Number(BigInt.asIntN(32, a[1])), idx = a[2], value = s64(a[3]), ptr = Number(u64(a[4])), opt = a[5];
    this.stats.dispatchByOp[op] = (this.stats.dispatchByOp[op] || 0) + 1;
    const g = inst.guest, h = this.hu8, rule = DISPATCH_RULES[op];
    let gptr = 0n, gvalue = value, post = null;
    if (ptr !== 0) {
      if (!rule) { this.stats.unmarshalled++; gptr = 0n; } // 規則の無い ptr は渡さない (別 memory ゆえ無効)
      else switch (rule.k) {
        case 'instr': { const s = this.readCStr(h, ptr, 1024); const p = g.space.alloc(s.length + 1); g.u8.set(Buffer.from(s + '\0', 'latin1'), p); gptr = BigInt(p); break; }
        case 'outstr': { const p = g.space.alloc(rule.n); g.u8.fill(0, p, p + rule.n);
          gptr = BigInt(p); post = () => { let L = 0; while (L < rule.n - 1 && g.u8[p + L]) L++; this.hu8.set(g.u8.subarray(p, p + L + 1), ptr); this.hu8[ptr + L] = 0; }; break; }
        case 'struct_out': { const p = g.space.alloc(rule.size); g.u8.fill(0, p, p + rule.size); gptr = BigInt(p);
          post = () => this.hu8.set(g.u8.subarray(p, p + rule.size), ptr); break; }
        case 'rectpp': { const p = g.space.alloc(8); g.u8.fill(0, p, p + 8); gptr = BigInt(p);
          post = (ret) => { if (ret === 0n) return; const rp = Number(g.dv.getBigUint64(p, true));
            if (!inst.rect) inst.rect = this.hexp.host_alloc(16);
            this.hu8.set(g.u8.subarray(rp, rp + 8), inst.rect); this.hdv.setBigUint64(ptr, BigInt(inst.rect), true); }; break; }
        case 'chunk_out': { const p = g.space.alloc(8); g.u8.fill(0, p, p + 8); gptr = BigInt(p);
          post = (ret) => { const sz = Number(ret); if (sz <= 0) return; const cp = Number(g.dv.getBigUint64(p, true));
            if (inst.chunkCap < sz) { inst.chunk = this.hexp.host_alloc(sz); inst.chunkCap = sz; }
            this.hu8.set(g.u8.subarray(cp, cp + sz), inst.chunk); this.hdv.setBigUint64(ptr, BigInt(inst.chunk), true); this.stats.bytesOut += sz; }; break; }
        case 'chunk_in': { const sz = Number(value); const p = g.space.alloc(sz); g.u8.set(h.subarray(ptr, ptr + sz), p); gptr = BigInt(p); this.stats.bytesIn += sz; break; }
        case 'events_in': gptr = BigInt(this.copyEvents(this.hdv, h, ptr, g.dv, g.u8, (n) => g.space.alloc(n))); break;
        case 'speaker_in': { // value=ptr(in), ptr=ptr(out)
          const copyArr = (src) => { const nch = this.hdv.getInt32(src + 4, true), sz = 8 + nch * 112; const p = g.space.alloc(sz); g.u8.set(h.subarray(src, src + sz), p); return p; };
          gptr = BigInt(copyArr(ptr)); if (value !== 0n) gvalue = BigInt(copyArr(Number(value))); break; }
        case 'handle': gptr = BigInt(ptr); break; // 不透明 (仮想 window ハンドル; GUI 設計 §2.6)
        default: throw new Error('hostbridge: bad rule ' + rule.k);
      }
    }
    const ret = g.call(pfn, [inst.pe, op, idx, gvalue, gptr, opt]);
    if (post) post(ret);
    return ret;
  }

  copyEvents(sdv, su8, sp, ddv, du8, alloc) { // VstEvents deep copy (Win64: numEvents@0, reserved@8, events[]@0x10)
    const nev = sdv.getInt32(sp, true), total = 0x10 + nev * 8, dp = alloc(total);
    du8.fill(0, dp, dp + total); ddv.setInt32(dp, nev, true);
    for (let i = 0; i < nev; i++) {
      const ep = Number(sdv.getBigUint64(sp + 0x10 + i * 8, true)), sz = Math.min(sdv.getInt32(ep + 4, true) + 8, 256);
      const dep = alloc(sz); du8.set(su8.subarray(ep, ep + sz), dep); ddv.setBigUint64(dp + 0x10 + i * 8, BigInt(dep), true);
    }
    return dp;
  }

  // ---- plugin → host (audioMaster) ----
  upcall(guest, eff, op, idx, vlo, vhi, ptr, opt) {
    this.stats.upcalls++;
    this.stats.upcallByOp[op] = (this.stats.upcallByOp[op] || 0) + 1;
    let inst = guest.byPe.get(eff >>> 0), cbIdx, effHost = 0n;
    if (inst) { cbIdx = inst.hostCbIdx; effHost = BigInt(inst.proxy); } else if (guest.entryCtx) cbIdx = guest.entryCtx.hostCbIdx; else throw new Error('hostbridge: upcall without context');
    const fn = this.hexp.__indirect_function_table.get(cbIdx);
    const value = (BigInt(vhi >>> 0) << 32n) | BigInt(vlo >>> 0);
    const rule = AM_RULES[op], gptr = ptr >>> 0;
    const hm = this.hostScratch.mark();
    let hptr = 0n, post = null, retStruct = null;
    try {
      if (gptr !== 0 && rule) {
        switch (rule.k) {
          case 'instr': { const s = this.readCStr(guest.u8, gptr, 1024); const p = this.hostScratch.alloc(s.length + 1); this.hu8.set(Buffer.from(s + '\0', 'latin1'), p); hptr = BigInt(p); break; }
          case 'outstr': { const p = this.hostScratch.alloc(rule.n); this.hu8.fill(0, p, p + rule.n); hptr = BigInt(p);
            post = () => { let L = 0; while (L < rule.n - 1 && this.hu8[p + L]) L++; guest.u8.set(this.hu8.subarray(p, p + L + 1), gptr); guest.u8[gptr + L] = 0; }; break; }
          case 'events_in': hptr = BigInt(this.copyEvents(guest.dv, guest.u8, gptr, this.hdv, this.hu8, (n) => this.hostScratch.alloc(n))); break;
          default: break;
        }
      } else if (gptr !== 0) this.stats.unmarshalled++;
      let r = fn(BigInt.asIntN(64, effHost), op, idx, BigInt.asIntN(64, value), BigInt.asIntN(64, hptr), opt);
      if (post) post();
      if (rule && rule.k === 'ret_struct' && r !== 0n) { // host ポインタ→guest scratch へコピーして guest ポインタを返す
        const hp = Number(u64(r)), p = guest.space.alloc(rule.size); guest.u8.set(this.hu8.subarray(hp, hp + rule.size), p); r = BigInt(p);
      }
      return Number(BigInt.asIntN(32, r));
    } finally { this.hostScratch.release(hm); }
  }
}
