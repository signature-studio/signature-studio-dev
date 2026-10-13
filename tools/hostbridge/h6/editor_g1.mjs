// editor_g1.mjs — HB-H6 (G1): effEdit* を宣言的 web UI に結線する HostBridge 拡張 (poc/hb_bridge.mjs は無改造; 継承のみ).
//
//   Fruity Wrapper が発行する editor 系 opcode (HOSTBRIDGE.md §1.3: 13/14/15/19) を guest へ転送せず UI 側で処理する:
//     effEditGetRect(13) : ptr=ERect** ← manifest の window 矩形 (top,left,bottom,right の int16×4)
//     effEditOpen(14)    : ptr=HWND (M7 の仮想 window 識別子; ここでは不透明値) → surface を取得, effGetParamName で
//                          manifest の param 名を index 解決, getParameter で初期値を取り込み初回描画
//     effEditIdle(19)    : FL タイマ. getParameter を引き直し (host 側 automation 追従), 変化があれば再描画
//     effEditClose(15)   : surface を解放
//   AEffect.flags は常に HasEditor(1) を立てて proxy へ見せる (plugin 自身は OTT: 0x18 = HasEditor 無し).
//   UI 操作 → guest.setParameter + audioMasterAutomate(op 0) を host へ upcall (VST2 の setParameterAutomated と同じ).
import { HostBridge } from '../poc/hb_bridge.mjs';
import { UiModel } from './ui_model.mjs';

export const EFF = { EditGetRect: 13, EditOpen: 14, EditClose: 15, EditIdle: 19, GetParamName: 8, GetParamDisplay: 7 };
const OFF = { dispatcher: 0x08, setParameter: 0x18, getParameter: 0x20, numParams: 0x2c, flags: 0x38 };
const bitsToF32 = (b) => { const u = new Uint32Array(1); u[0] = Number(BigInt.asUintN(32, b)); return new Float32Array(u.buffer)[0]; };
const f32ToBits = (f) => { const a = new Float32Array(1); a[0] = f; return BigInt(new Uint32Array(a.buffer)[0]); };

export class HostBridgeG1 extends HostBridge {
  // editors: uniqueID(int32) -> { manifest, assets, surface(hwnd) -> {present(list, model)} }
  constructor(table, editors) {
    super(table);
    this.editors = editors; this.g1 = { opens: 0, closes: 0, idles: 0, redraws: 0, automates: [], rectCalls: 0 };
  }

  callEntry(slot, a) {
    const r = super.callEntry(slot, a);
    if (r !== 0n) this.forceHasEditor(Number(r));
    return r;
  }
  syncOut(inst) { // plugin 所有欄の同期後に HasEditor を OR (guest は立てない)
    super.syncOut(inst);
    this.forceHasEditor(inst.proxy);
  }
  forceHasEditor(proxy) {
    if (!this.editors.has(this.hdv.getInt32(proxy + 0x70, true))) return;
    const h = this.hdv; h.setInt32(proxy + OFF.flags, h.getInt32(proxy + OFF.flags, true) | 1, true);
  }

  doDispatch(inst, pfn, a) {
    const op = Number(BigInt.asIntN(32, a[1]));
    if ((op === EFF.EditGetRect || op === EFF.EditOpen || op === EFF.EditClose || op === EFF.EditIdle) && this.edDesc(inst)) {
      this.stats.dispatch++; this.stats.dispatchByOp[op] = (this.stats.dispatchByOp[op] || 0) + 1;
      return this.editorDispatch(inst, op, Number(BigInt.asUintN(64, a[4])));
    }
    return super.doDispatch(inst, pfn, a);
  }

  edDesc(inst) { return this.editors.get(this.hdv.getInt32(inst.proxy + 0x70, true)) || null; }

  // ---- guest 呼出 (host 呼出の外 = UI イベントからも使うので mark/release を自前で持つ) ----
  gcall(inst, fn, args) {
    const g = inst.guest, m = g.space.mark();
    try { return g.call(g.dv.getBigUint64(inst.pe + OFF[fn], true), [inst.pe, ...args]); } finally { g.space.release(m); }
  }
  gParamName(inst, i) {
    const g = inst.guest, m = g.space.mark(), p = g.space.alloc(64);
    try { g.u8.fill(0, p, p + 64); this.gcall(inst, 'dispatcher', [EFF.GetParamName, i, 0, p, 0]); let s = '', k = 0; while (k < 63 && g.u8[p + k]) s += String.fromCharCode(g.u8[p + k++]); return s; }
    finally { g.space.release(m); }
  }
  gParamDisplay(inst, i) {
    const g = inst.guest, m = g.space.mark(), p = g.space.alloc(64);
    try { g.u8.fill(0, p, p + 64); this.gcall(inst, 'dispatcher', [EFF.GetParamDisplay, i, 0, p, 0]); let s = '', k = 0; while (k < 63 && g.u8[p + k]) s += String.fromCharCode(g.u8[p + k++]); return s; }
    finally { g.space.release(m); }
  }
  gGet(inst, i) { return bitsToF32(this.gcall(inst, 'getParameter', [i])); }

  editorDispatch(inst, op, ptr) {
    const d = this.edDesc(inst);
    switch (op) {
      case EFF.EditGetRect: { // ERect** : { int16 top, left, bottom, right }
        this.g1.rectCalls++;
        if (!inst.g1rect) inst.g1rect = this.hexp.host_alloc(16);
        const w = d.manifest.window, h = this.hdv;
        h.setInt16(inst.g1rect, 0, true); h.setInt16(inst.g1rect + 2, 0, true); h.setInt16(inst.g1rect + 4, w.height, true); h.setInt16(inst.g1rect + 6, w.width, true);
        h.setBigUint64(ptr, BigInt(inst.g1rect), true);
        return 1n;
      }
      case EFF.EditOpen: {
        if (inst.ed) return 0n;
        const surface = d.surface(BigInt(ptr));
        if (!surface) return 0n;
        const n = this.hdv.getInt32(inst.proxy + OFF.numParams, true), names = [];
        for (let i = 0; i < n; i++) names.push(this.gParamName(inst, i));
        const model = new UiModel(d.manifest, d.assets, { onChange: (idx, v) => this.uiChange(inst, idx, v) });
        const { missing } = model.resolve(names);
        if (missing.length) { this.g1.lastMissing = missing; return 0n; }
        const ed = inst.ed = { model, surface, hwnd: BigInt(ptr), names };
        model.setValues((i) => this.gGet(inst, i));
        this.paint(inst, ed);
        this.g1.opens++;
        return 1n;
      }
      case EFF.EditIdle: {
        this.g1.idles++;
        const ed = inst.ed; if (!ed) return 0n;
        if (ed.model.setValues((i) => this.gGet(inst, i)).length) this.paint(inst, ed);
        return 0n;
      }
      case EFF.EditClose: {
        if (!inst.ed) return 0n;
        if (inst.ed.surface.close) inst.ed.surface.close();
        inst.ed = null; this.g1.closes++;
        return 0n;
      }
    }
    return 0n;
  }

  paint(inst, ed) {
    const disp = (c) => this.gParamDisplay(inst, c.index);
    ed.surface.present(ed.model.displayList(disp), ed.model); this.g1.redraws++;
  }

  // UI → plugin: setParameter + audioMasterAutomate(op 0, index, opt=value)
  uiChange(inst, idx, v) {
    this.gcall(inst, 'setParameter', [idx, f32ToBits(v)]);
    const fn = this.hexp.__indirect_function_table.get(inst.hostCbIdx);
    fn(BigInt(inst.proxy), 0, idx, 0n, 0n, v);
    this.g1.automates.push({ idx, v });
    if (inst.ed) this.paint(inst, inst.ed);
  }

  // surface (Canvas の pointer イベント) から呼ぶ入口
  pointer(inst, kind, x, y, opts) { const m = inst.ed && inst.ed.model; if (!m) return false; return kind === 'down' ? m.pointerDown(x, y) : kind === 'move' ? m.pointerMove(x, y, opts) : m.pointerUp(); }
}
