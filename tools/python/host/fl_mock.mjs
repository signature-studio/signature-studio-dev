// FLEngine 模擬ホスト (PoC)。実装版では FLEngine wasm の export に置換される同一インタフェース:
//   engine.call("mixer.getTrackName", [index, ...]) -> any
// 返す number は整数なら int、実数なら float になる。整数値の float は F(x) で明示。
import { createIlmcp } from "./ilmcp.mjs";
const F = (v) => ({ t: "D", v });
// PY-100 (#2879): PE 0xd5b930 の readout (C provider と同一)。構造体 = grid bit が立つ step。範囲外は -1
// PY-111 (#2929): note の生成経路の PE 値 (C provider と同一)。param 5/6 = 128・param 7 = step × 24 (V 静的)・param 8 = 0
// PY-228 (#3656): plugin パラメータの既定値 (インスタンスごとの値 pv / spv の初期値。provider/fl_engine.c の params[] と同じ)
const STEP_V = 24;
const FCC_N = 16; // PY-276 (#3949): forwardMIDICC の添字範囲 (provider/fl_engine.c の FCC_N と同じ仮置き)
const STEP_DEF = [60, 100, 64, 120, 64, 128, 128, 0, 0];
const PARAM_DEFAULT = [0.5, 0.2, 0.8];
const stepParam = (k, pos, prm) => (pos < 0 || pos >= 64 || !k.steps[pos] || prm < 0 || prm > 8 ? -1 : prm === 7 ? pos * STEP_V : prm === 1 ? (k.vel?.[pos] ?? STEP_DEF[1]) : STEP_DEF[prm]);
// PY-224 (#3628): PE 0x12d3ff0 の loop 分岐 (C provider の grid_bit_loop と同一・REPORT_PY224)。行 T[1] と flag49e・flag54 が立ち、channel i の最初の record (f4 != 0) が L = len / 24 を与えるとき、p < L は base、それ以外は base(p mod L)
const LOOP_G2 = 24;
const LOOP_MAX = 8;
const loopBit = (st, i, k, p) => {
  p |= 0;
  const base = gridBit(st, i, k, p);
  if (!st.loop.row || !st.loop.flag49e || !st.loop.flag54) return base;
  const rec = st.loop.recs.find((r) => r.cid === i && r.f4 !== 0);
  if (!rec) return base;
  const L = Math.trunc(rec.len / LOOP_G2);
  if (L <= 0 || p < L) return base;
  return gridBit(st, i, k, p % L);
};

class FlError extends Error {
  constructor(msg, code) { super(msg); this.flCode = code; }
}
const RANGE = (m) => new FlError(m || "Index out of range", 4);
const UNSAFE = () => new FlError("Operation unsafe at current time", 3);
// PY-76 (#2563): cvtsd2si (64bit・最近接偶数丸め)。範囲外と inf は 0x8000000000000000 (INT64_MIN) (REPORT_PY72 §callback unit 2)
const cvtSi64 = (x) => {
  if (!(x >= -(2 ** 63) && x < 2 ** 63)) return -(2 ** 63);
  const f = Math.floor(x), d = x - f;
  return d < 0.5 ? f : d > 0.5 ? f + 1 : (f % 2 === 0 ? f : f + 1);
};
const WRONG = (m) => new FlError(m || "Wrong number of function parameters or wrong parameter type", 5);
// PY-235 (#3701): processRECEvent の成功経路の family (REPORT_PY235)。eventId は uint32。戻り値 = value になるのは R-other かつ (eventId & 0xffff) != 8 のとき
// 固定 4 族 (0x40000000/1/2/5) は flags & 0x22 == 0 のとき store 0 件で value を返す (REPORT_PY252)。flags & 0x22 の分岐は engine 状態依存のため未確定
const recPassFamily = (e, f) => (e & 0xffff) !== 8 && ((e >= 0x10000000 && e < 0x40000000) || (e >= 0x40000003 && e <= 0x40000004) || (e > 0x40000005 && e < 0x70000000) || e >= 0xf0000000 || ([0x40000000, 0x40000001, 0x40000002, 0x40000005].includes(e) && (f & 0x22) === 0));
// mixer の色の R/B 入替え (REPORT_PY115.md §2)。既定色は FL の .bss 0x15f6774 の初期値 (REPORT_PY118)
const swapRb = (v) => ((v & 0xff) << 16) | (v & 0xff00) | ((v >>> 16) & 0xff);
const MIX_DEFAULT_COLOR = 0xff636c71;
// PY-172 (#3219): パターングループ数の仮置き (未実測・REPORT_PY172)。件数 0 では getPatternGroupName の全索引が範囲外
const PGRP_N = 0;
// PY-179 (#3271): 述語 pred の静的状態 (未投入で偽) から導く仮置き・patternNumber の PE 初期値 1 (provider/fl_engine.c の PAT_N・PAT_NUMBER と同じ・REPORT_PY179)
const PAT_N = 999;
const PAT_NUMBER = 1;
// PY-78 (#2581): PE 0x130f3d0 の項目書換え規則 (C provider の step_item_write / step_items_set と同一・REPORT_PY39_2548.md)。項目 = 字段の object
const clampHi = (v, hi) => (v <= 0 ? 0 : v > hi ? hi : v);
const newItem = () => ({ d0: 0, w0c: 0, b10: 0, b11: 0, b12: 0, b14: 0, b15: 0, b16: 0, b17: 0 });
const itemGet = (it, prm) => ({ 0: it.w0c, 1: it.b15, 2: it.b12, 3: it.b10, 4: it.b14, 5: it.b16, 6: it.b17, 7: it.d0, 8: it.b11 })[prm] ?? 0;
const itemWrite = (it, prm, value, delta) => {
  switch (prm) {
    case 0: it.w0c = clampHi(it.w0c + delta, 0x83); break;
    case 1: it.b15 = clampHi(it.b15 + delta, 0x80); break;
    case 2: it.b12 = clampHi(it.b12 + delta, 0x80); break;
    case 3: it.b10 = clampHi(it.b10 + delta, 0xf0); break;
    case 4: it.b14 = clampHi(it.b14 + delta, 0x80); break;
    case 5: it.b16 = clampHi(it.b16 + delta, 0xff); break;
    case 6: it.b17 = clampHi(it.b17 + delta, 0xff); break;
    case 7: it.d0 = (it.d0 + delta) | 0; break;
    case 8: it.b11 = value & 0xff; break;
  }
};
const itemsSet = (items, prm, value) => {
  if (!items.length || prm < 0 || prm > 8) return;
  const delta = prm === 8 ? value : value - itemGet(items[0], prm);
  for (const it of items) itemWrite(it, prm, value, delta);
};
// PY-184 (#3309): 項目列挙 PE 0x130f200 の判定式 (C provider の note_enum と同一・REPORT_PY39_2548.md)。note = 項目 (字段 +0 start・+6 ch・+8 len)。note 配列は start 昇順が前提
const noteGen = (seed, n) => {
  let s = seed >>> 0;
  const next = () => { s = (Math.imul(s, 1103515245) + 12345) >>> 0; return s >>> 16; };
  const arr = Array.from({ length: Math.min(Math.max(n, 0), 256) }, () => {
    const d0 = (next() % 200) - 50;
    const len = (next() % 40) - 5;
    const ch = next() % 4;
    return { ...newItem(), d0, len, ch };
  });
  return arr.sort((a, b) => a.d0 - b.d0);
};
const noteEnum = (arr, chan, step, V) => {
  const out = [];
  if (V <= 0) return out;
  const thr = (step + V) | 0;
  for (let cur = 0; cur < arr.length && arr[cur].d0 < thr; cur++) {
    const it = arr[cur];
    const sq = (Math.trunc(it.d0 / V) * V) | 0;
    const end = Math.max((it.d0 + Math.max(it.len, 1)) | 0, (sq + V - 1) | 0);
    if (step < sq || step >= end || it.ch !== (chan >>> 0)) continue;
    out.push(cur);
  }
  return out;
};
// PY-218 (#3596): 件数超え (position >= 件数) の event 経路 PE 0x12d3e20 (REPORT_PY218.md)。閾値は (position+1)*V、V = 24 (PE [0x15e25f8]・REPORT_APPENDIX_3310)。32bit 演算 (PE の imul/add と同じ)
// PY-288 (#3985): 件数 GRID_N = ceil(L/96)*4 (既定 L = 384 で 16・REPORT_PY225 PY-230 節)。C provider の GRID_N と同じ
const GRID_N = 16;
const GRID_V = 24;
const gridGen = (seed, n) => {
  let s = seed >>> 0;
  const next = () => { s = (Math.imul(s, 1103515245) + 12345) >>> 0; return s >>> 16; };
  const arr = Array.from({ length: Math.min(Math.max(n, 0), 256) }, () => {
    const d0 = (next() % 2000) - 200;
    const ch = next() % 4;
    const flag = next() & 0xff;
    return { d0, ch, flag };
  });
  return arr.sort((a, b) => a.d0 - b.d0);
};
const gridEvent = (items, index, p) => {
  const lo = Math.imul(p, GRID_V) | 0, hi = (lo + GRID_V) | 0;
  let cur = 0;
  while (cur < items.length && items[cur].d0 < lo) cur++;
  for (; cur < items.length && items[cur].d0 < hi; cur++) {
    if (items[cur].ch === index && !(items[cur].flag & 0x20)) return true;
  }
  return false;
};
const gridBit = (st, index, k, p) => {
  p |= 0;
  if (p < 0) return false;
  if (p >= GRID_N) return gridEvent(st.gridItems, index, p);
  return !!k.steps[p];
};

export function createMockEngine() {
  const st = {
    tempo: 130,
    playing: false,
    changedFlag: 0, useMetronome: false, precount: false, recPPQ: 96,
    launchPages: 0,
    uiClosing: false, uiTimeDispMin: false, uiStartOnInput: false, uiLoopRec: false, uiStepEdit: false, uiBrowserAutoHide: false, uiSnapMode: 0,
    keys: [],
    undoPos: 0, undoCount: 0, undoLast: 0, safeEdit: true, projTitle: "", projAuthor: "", projGenre: "",
    selStart: -1, selEnd: -1, liveAnchor: -1,
    arrTime: 0,
    numerator: 4, denominator: 4,
    screenBlanked: false, screenUnBlank: false, screenActiveCounter: 0, screenDefaultCounter: 0,
    screenAlive: false, screenDirty: false, screenMenuShowing: false, screenSetup: { l: 0, t: [0, 0, 0, 0, 0] },
    selectedChannel: 0,
    loop: { row: false, flag49e: false, flag54: false, recs: [] },
    gridItems: [],
    channels: [
      { name: "Kick", plugin: "Sampler", vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: true, fx: 1, steps: new Array(64).fill(0), pitchN: 2, pv: [...PARAM_DEFAULT] },
      { name: "Snare", plugin: "Sampler", vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: false, fx: 2, steps: new Array(64).fill(0), pitchN: 2, pv: [...PARAM_DEFAULT] },
      { name: "3x Osc", plugin: "3x Osc", vol: 0.5, pan: 0.25, mute: false, solo: false, color: 0x7C5A6B, sel: false, fx: 0, steps: new Array(64).fill(0), pitchN: 2, pv: [...PARAM_DEFAULT] },
    ],
    mixer: Array.from({ length: 127 }, (_, i) => ({
      name: i === 0 ? "Master" : i === 125 ? "Current" : `Insert ${i}`, vol: 0.8, pan: 0, mute: false, solo: false,
      color: 0, colorSet: false, sel: i === 0, slots: [], spv: [], routes: i === 0 ? {} : { 0: 1.0 },
    })),
    playlist: Array.from({ length: 500 }, (_, i) => ({ name: `Track ${i + 1}`, color: 0x485156, lock: 0, act: 0, loop: 0, trigMode: 0, posSnap: 0, trigSnap: 0 })),
    windows: { 0: true, 1: false, 2: true, 3: false, 4: true, 5: false },
    displayTime: 0,
    browserOp: 0,
    params: [{ name: "Cutoff", v: 0.5 }, { name: "Resonance", v: 0.2 }, { name: "Gain", v: 0.8 }],
    prScripts: {},
    midiOut: [],
    idleElapsed: 0, midiOutAssigned: false, masterSync: false,
    // PY-227 (#3655): device 割当 (false で -7)・送出先 (false で -6)。既定は両方あり (provider/fl_engine.c と同じ)
    devAssigned: true,
    linkAssigned: true,
    // PY-276 (#3949): forwardMIDICC の添字ごとの最後の送った値 (-1 は未設定)。範囲は C と同じ FCC_N
    fccLast: Array.from({ length: FCC_N }, () => -1),
    log: [],
  };
  // channels / playlist の index は整数のみ (C provider の A_INT と同じ: 文字列・None・非整数は code 5)、範囲外は code 4
  const ix = (i) => { if (i === undefined) return 0; if (typeof i === "boolean") return +i; if (!Number.isInteger(i)) throw WRONG(); return i; };
  const str = (s) => { if (typeof s !== "string") throw WRONG(); return s; };
  const ch = (i) => { i = ix(i); if (!st.channels[i]) throw RANGE(); return st.channels[i]; };
  const pl = (i) => { i = ix(i); if (i < 1 || i > st.playlist.length) throw RANGE(); return st.playlist[i - 1]; };
  const tr = (i) => { if (!st.mixer[i]) throw RANGE(); return st.mixer[i]; };
  // PY-228 (#3656): plugin パラメータの解決 (provider/fl_engine.c の pinst と同じ順)。slot -1 は channel、slot >= 0 は mixer track の insert slot。
  // 範囲外は code 4、空 slot は code 8 (Plugin not valid)、paramIndex は [0, 既定値の件数)。
  const plugPV = (i, slot, p) => {
    let pv;
    if (slot === -1) pv = ch(i).pv;
    else {
      const t = tr(ix(i));
      if (slot < 0 || slot >= 10) throw RANGE();
      if (!t.slots[slot]) throw new FlError("Plugin not valid", 8);
      pv = t.spv[slot];
    }
    p = ix(p);
    if (p < 0 || p >= pv.length) throw RANGE();
    return [pv, p];
  };
  const tog = (cur, v) => (v === undefined || v === -1 ? !cur : !!v);
  // PE 0x12be470 (maxLen > 0 のみ): JS 文字列は PE と同じ UTF-16 code unit で数える。長さが maxLen を超える間、末尾から mask 外の unit (母音・記号・空白・非 ASCII) を 1 unit ずつ削り、先頭 maxLen unit へ切る。切れた境界の孤立サロゲートは U+FFFD (C provider の track_name_fit と同一)
  const KEEP = new Set("0123456789BCDFGHJKLMNPQRSTVWXYZ");
  const fitName = (s, m) => {
    if (m <= 0 || s.length <= m) return s;
    let t = s;
    for (let i = t.length; i >= 1 && t.length > m; i--) {
      const c = t[i - 1];
      if (!KEEP.has(c >= "a" && c <= "z" ? c.toUpperCase() : c)) t = t.slice(0, i - 1) + t.slice(i);
    }
    return t.slice(0, m).replace(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g, "\uFFFD");
  };
  // fl_provider の引数検査 (fl_dispatch.c type_ok / fl_a_int) と同じ: None は既定値、bool と整数のみ可、他は code 5
  const argI = (a, i, def) => {
    const v = a[i];
    if (i >= a.length || v === undefined) return def;
    if (typeof v === "boolean") return +v;
    if (Number.isInteger(v)) return v;
    throw WRONG();
  };
  const arity = (a, lo, hi) => { if (a.length < lo || a.length > hi) throw WRONG(); };
  // PY-246 (#3759): 送出キーの記録 (C の key_send と同じ: 回数 <= 0 は送出 leaf に入らない)
  const sendKey = (vk, mod, count) => { if (count > 0) st.keys.push({ vk, mod, count: Math.min(count, 0x7fffffff) }); };
  // PyArg "i" 相当 (C provider の 'I'/'B' のみ可): None・文字列・実数は code 5
  const pyInt = (v) => { if (typeof v === "boolean") return +v; if (Number.isInteger(v)) return v; throw WRONG(); };
  // float 引数 (fl_a_dbl と同じ: None は 0、bool・整数・実数は可、他は code 5)。PE の書式 'f' は float32 に丸める
  const argF = (a, i) => { const v = a[i]; if (i >= a.length || v === undefined) return 0; if (typeof v === "boolean") return +v; if (typeof v === "number") return Math.fround(v); throw WRONG(); };
  const scrNeed = () => { if (!st.screenAlive) throw new FlError("Unspecified error", 2); };
  // fl_a_dbl と同じ (plugins.setParamValue の値): None は 0、bool・実数は可 (丸めない)、他は code 5
  const argD = (a, i) => { const v = a[i]; if (i >= a.length || v === undefined) return 0; if (typeof v === "boolean") return +v; if (typeof v === "number") return v; throw WRONG(); };
  // plugins の値 API の引数は C と同じ順に型検査してから解決する (paramIndex・index・slotIndex・useGlobalIndex・(setParamValue の pickupMode))。o = paramIndex の位置、n = 最大個数
  const plugIn = (a, o, n) => { const q = argI(a, o, 0), i = argI(a, o + 1, 0), s = argI(a, o + 2, -1); for (let k = o + 3; k < n; k++) argI(a, k, 0); return plugPV(i, s, q); };
  const disp = (a, lo, hi, ti) => { arity(a, lo, hi); const v = Array.from({ length: hi }, (_, i) => argI(a, i, 0)); st.displayTime = Math.min(v[ti], 0x7d0); };
  // PY-144 (#3043): PE 0xe43d30 の書込み規則。start=x・end=y を置き、x==y なら end=-1、x>y なら入れ替える。selectionClear は (-1,-1) で同じ経路
  const selSet = (x, y) => { st.selStart = x; st.selEnd = y; if (x === y) st.selEnd = -1; else if (x > y) { st.selStart = y; st.selEnd = x; } };
  // PY-254 (#3796): PE 0xe43ff0 (liveSelection) の a≠0x7fffffff 経路。b==1 なら anchor (≥0 かつ a と異なる) から a までを選択し anchor=-1。それ以外は選択を (-1,-1)。b!=1 は anchor=a。anchor の初期値 -1 は仮置き
  const liveSel = (a, b) => {
    const flag = b === 1, anc = st.liveAnchor;
    if (flag && anc >= 0 && anc !== a) selSet(anc, a); else selSet(-1, -1);
    st.liveAnchor = flag ? -1 : a;
  };

  const impl = {
    "channels.channelCount": () => st.channels.length,
    "channels.selectedChannel": (...a) => {
      arity(a, 0, 3);
      const offset = argI(a, 1, 0);
      argI(a, 0, 0); argI(a, 2, 0);
      return st.selectedChannel + offset;
    },
    // fl_engine.c の順に検査: 先頭 index → stride/offset/vel/5 番目 (型) → stride<1 は RANGE (ループに入らない)。
    // 5 番目引数 useGlobalIndex は未モデル化 (型検査のみ、値は見ない)。6 番目以降は無視
    "channels.fillEachNSteps": (...a) => {
      const ci = argI(a, 0, 0);
      ch(ci);
      const stride = argI(a, 1, 1), offset = argI(a, 2, 0);
      const vel = Math.min(Math.max(argI(a, 3, 100), 0), 127);
      argI(a, 4, 0);
      if (stride < 1) throw RANGE();
      let p = offset;
      if (p < 0) { p = offset % stride; if (p < 0) p += stride; }
      for (; p < 64; p += stride) { const k = ch(ci); k.steps[p] = 1; (k.vel ??= [])[p] = vel; }
    },
    "channels.getChannelName": (i) => ch(i).name,
    "channels.setChannelName": (i, n) => { ch(i).name = str(n); },
    "channels.isChannelSelected": (i) => ch(i).sel,
    // PY-41 (#1514): 公開 stub の戻り型と説明で決めた 5 関数 (C provider と同一)。useGlobalIndex は未モデル
    "channels.isChannelMuted": (...a) => { arity(a, 1, 2); argI(a, 1, 0); return ch(a[0]).mute; },
    "channels.isChannelSolo": (...a) => { arity(a, 1, 2); argI(a, 1, 0); return ch(a[0]).solo; },
    "channels.getChannelColor": (...a) => { arity(a, 1, 2); argI(a, 1, 0); return ch(a[0]).color; },
    // PY-101 (#2878) / PY-112 (#2932): PE 0xd5b420 は position の範囲検査を持たない。position<0 は 0、件数以上は event 経路 (PY-218・gridBit)
    "channels.getGridBit": (...a) => {
      arity(a, 2, 3);
      const index = ix(a[0]); const p = ix(a[1]); argI(a, 2, 0);
      const k = ch(index);
      return gridBit(st, index, k, p);
    },
    // PY-101 (#2878): PE 0xd5b360 は grid (+0x7ac) 非 null で True。mock の channel は生成時に grid を持つものとして扱い、null 経路は持たない (C と同一)
    "channels.isGridBitAssigned": (...a) => {
      arity(a, 1, 2);
      ix(a[0]); argI(a, 1, 0);
      ch(a[0]);
      return true;
    },
    // PY-101 (#2878) / PY-112 (#2932): PE 0xd5bc10 → 0x12d3ff0。base は gridBit (件数以上は event 経路・PY-218)。loop 分岐は PY-224 (#3628) の loopBit
    "channels.getGridBitWithLoop": (...a) => {
      arity(a, 2, 3);
      const index = ix(a[0]); const p = ix(a[1]); argI(a, 2, 0);
      const k = ch(index);
      return loopBit(st, index, k, p);
    },
    // 選択の並びで offset 番目 (負は先頭扱い・仮置き)、超えたら最後の選択。無選択は canBeNone で -1 / 0
    "channels.channelNumber": (...a) => {
      arity(a, 0, 2);
      const none = argI(a, 0, 0), off = Math.max(0, argI(a, 1, 0));
      const sel = st.channels.flatMap((c, i) => (c.sel ? [i] : []));
      if (!sel.length) return none ? -1 : 0;
      return sel[Math.min(off, sel.length - 1)];
    },
    // PY-41 (#1514): stub midi.CT_Sampler = 0 / CT_GenPlug = 2 を plugin 名で決める (C と同一・Hybrid 等は未モデル)
    "channels.getChannelType": (...a) => { arity(a, 1, 2); argI(a, 1, 0); return ch(a[0]).plugin === "Sampler" ? 0 : 2; },
    // PY-100 (#2879): PE 0xd5bb30 / 0xd5ba00 (C と同一)。引数を読んでから index を検査。padsStride 既定 16、0 は Range error
    "channels.getCurrentStepParam": (...a) => {
      arity(a, 3, 4);
      const step = argI(a, 1, 0), prm = argI(a, 2, 0); argI(a, 3, 0);
      return stepParam(ch(a[0]), step, prm);
    },
    "channels.getStepParam": (...a) => {
      arity(a, 4, 5);
      const step = argI(a, 0, 0), prm = argI(a, 1, 0), off = argI(a, 2, 0), st0 = argI(a, 3, 0), pads = argI(a, 4, 16);
      if (pads === 0) throw new FlError("Range error", 4);
      const q = Math.trunc(step / pads), idx = q + off;
      if (idx < 0 || idx >= st.channels.length) throw RANGE();
      return stepParam(st.channels[idx], step - q * pads + st0, prm);
    },
    // PY-89 (#2805): C と同一。identity (全 channel が 1 グループ)・既定 -2 (未割当)
    "channels.getChannelIndex": (...a) => { arity(a, 1, 1); const i = ix(a[0]); ch(i); return i; },
    "channels.getChannelMidiInPort": (...a) => { arity(a, 1, 2); ch(a[0]); argI(a, 1, 0); return -2; },
    "channels.selectChannel": (i, v) => { ch(i).sel = tog(ch(i).sel, v); },
    "channels.deselectAll": () => { st.channels.forEach((c) => (c.sel = false)); },
    // PE 0xd5afc0 → 0x11e84a0: 対象だけ選択し他は解除 (useGlobalIndex は未モデル・C と同じ)
    "channels.selectOneChannel": (...a) => {
      arity(a, 1, 2);
      const k = ch(a[0]);
      argI(a, 1, 0);
      st.channels.forEach((c) => (c.sel = c === k));
    },
    "channels.muteChannel": (i, v) => { ch(i).mute = tog(ch(i).mute, v); },
    // PE 0xd59b40 → 0xd843d0: value == -1 は反転、他は現在値の下位 1 B と一致すれば不変・不一致なら反転 (C と同一)。useGlobalIndex は未モデル (型検査のみ)
    "channels.soloChannel": (...a) => {
      const k = ch(a[0]);
      const v = argI(a, 1, -1);
      argI(a, 2, 0);
      if (v === -1 || (v & 0xff) !== +k.solo) k.solo = !k.solo;
    },
    "channels.getChannelVolume": (i, mode) => F(mode ? 20 * Math.log10(Math.max(ch(i).vol, 1e-6) / 0.78125) : ch(i).vol),
    "channels.setChannelVolume": (i, v) => { ch(i).vol = v; },
    "channels.getChannelPan": (i) => F(ch(i).pan),
    "channels.setChannelPan": (i, v) => { ch(i).pan = v; },
    // PY-76 (#2563): C provider (fl_engine.c setChannelPitch) と同一。判定順は index 範囲外 (-4) → NaN (-1) → pitchUnit。unit 0/1 の効果・guard・通知は未モデル (unit 2 だけ N を書く)
    "channels.setChannelPitch": (...a) => {
      arity(a, 2, 5);
      const i = ix(a[0]); const v = argF(a, 1); const unit = argI(a, 2, 0); argI(a, 3, 0); argI(a, 4, 0);
      const k = ch(i);
      if (Number.isNaN(v)) throw new FlError("Unspecified error", 2);
      if (unit === 2) k.pitchN = Math.min(48, Math.max(1, cvtSi64(v)));
    },
    "channels.setChannelColor": (i, c) => { ch(i).color = c; },
    "channels.getTargetFxTrack": (i) => ch(i).fx,
    "channels.setTargetFxTrack": (i, t) => { ch(i).fx = t; },
    "channels.setGridBit": (i, pos, v) => {
      const k = ch(i);
      pos = ix(pos);
      if (pos < 0 || pos >= 64) throw RANGE();
      k.steps[pos] = v ? 1 : 0;
      if (v) (k.vel ??= [])[pos] = 100;
    },
    "channels.quickQuantize": (i) => { ch(i); },
    "channels.showEditor": (i) => { ch(i); },
    // PY-40 (#1529): PE 0xd5ca50 / 0xd5c920 / 0xd5cbd0 / 0xd5c180 / 0xd5c5d0 (C provider と同一)。index は 0..件数-1 (範囲外 code 4)。述語・UI 副作用は未モデル
    "channels.closeGraphEditor": (...a) => { arity(a, 1, 1); argI(a, 0, 0); },
    "channels.updateGraphEditor": (...a) => { arity(a, 0, 0); },
    "channels.showGraphEditor": (...a) => {
      arity(a, 4, 5);
      argI(a, 0, 0); argI(a, 1, 0); argI(a, 2, 0);
      const idx = argI(a, 3, 0);
      argI(a, 4, 1);
      if (idx < 0 || idx >= st.channels.length) throw RANGE();
    },
    "channels.showCSForm": (...a) => {
      arity(a, 1, 3);
      const idx = argI(a, 0, 0); argI(a, 1, 1); argI(a, 2, 0);
      if (idx < 0 || idx >= st.channels.length) throw RANGE();
    },
    "channels.focusEditor": (...a) => {
      arity(a, 1, 2);
      const idx = argI(a, 0, 0); argI(a, 1, 0);
      if (idx < 0 || idx >= st.channels.length) throw RANGE();
    },
    "mixer.trackCount": () => st.mixer.length,
    // PE 0xd641d0: ポインタ大域 0x15e2198 の指す先の dword を読んで −2 (trackCount 0xd5e8b0 と同じ読み方・REPORT_PY205)
    "mixer.getTrackCount": () => st.mixer.length - 2,
    // PE 0xd63870: ecx=3 を変換スロット 0x15e4280 に渡すのみ (REPORT_PY205)
    "mixer.getEqBandCount": () => 3,
    "mixer.getTrackName": (...a) => fitName(tr(a[0]).name, argI(a, 1, -1)),
    "mixer.setTrackName": (i, n) => { tr(i).name = n; },
    "mixer.getTrackVolume": (i, mode) => F(mode ? 20 * Math.log10(Math.max(tr(i).vol, 1e-6) / 0.8) : tr(i).vol),
    "mixer.setTrackVolume": (i, v) => { tr(i).vol = v; },
    "mixer.getTrackPan": (i) => F(tr(i).pan),
    "mixer.setTrackPan": (i, v) => { tr(i).pan = v; },
    "mixer.setTrackColor": (i, c) => { const t = tr(i); t.color = (swapRb(c) | 0xff000000) >>> 0; t.colorSet = true; },
    // PE 0xd5ec60: idx < 0 は例外でなく int 0 (警告は初回のみ。mock は表示しない)。idx ≥ 127 は RANGE (C と同じ)
    "mixer.getTrackColor": (i) => { if (i < 0) return 0; const t = tr(i); return (swapRb(t.colorSet ? t.color : swapRb(MIX_DEFAULT_COLOR)) | 0xff000000) >>> 0; },
    "mixer.isTrackSelected": (i) => tr(i).sel,
    "mixer.muteTrack": (i, v) => { tr(i).mute = tog(tr(i).mute, v); },
    "mixer.soloTrack": (i) => { tr(i).solo = !tr(i).solo; },
    "mixer.getRouteSendActive": (s, d) => d in tr(s).routes,
    "mixer.setRouteTo": (s, d, v) => { if (v) tr(s).routes[d] = tr(s).routes[d] ?? 1.0; else delete tr(s).routes[d]; },
    "mixer.getRouteToLevel": (s, d) => F(tr(s).routes[d] ?? 0),
    "mixer.setRouteToLevel": (s, d, v) => { tr(s).routes[d] = v; },
    "mixer.focusEditor": (i) => { tr(i); },
    // MCPTools は getCurrentTempo(1) / setCurrentTempo(bpm, 1) を素の BPM として扱う (clamp 10..522)。
    // 公式 docs の asInt は ×1000 整数の記述 → 実機での意味は要確認 (本モックは MCPTools の使い方に合わせ整数 BPM)。
    "mixer.getCurrentTempo": (asInt) => (asInt ? Math.round(st.tempo) : F(st.tempo)),
    "mixer.setCurrentTempo": (bpm) => { st.tempo = bpm >= 10000 ? bpm / 1000 : bpm; },
    "transport.start": () => { st.playing = true; },
    "transport.stop": () => { st.playing = false; },
    "transport.isPlaying": (...a) => { arity(a, 0, 0); return st.playing; },
    "playlist.trackCount": () => st.playlist.length,
    "playlist.getTrackName": (i) => { i = ix(i); return st.playlist[i - 1]?.name ?? ""; }, // 範囲外は空文字 (C と同じ)
    "playlist.setTrackName": (i, n) => { pl(i).name = str(n); },
    "playlist.setTrackColor": (i, c) => { pl(i).color = (((c & 0xff) << 16) | (c & 0xff00) | ((c >>> 16) & 0xff)) & 0xffffff; }, // FL の格納式 (C と同じ)
    // PY-62 (#2027): REPORT_PY61 §2 で確定した 8 関数 (C provider と同一)。既定値は 0 の仮置き。引数検査は C の dispatch と同じ順 (型 → 範囲)
    "playlist.getTrackColor": (...a) => { arity(a, 1, 1); const u = pl(a[0]).color >>> 0; return (((u & 0xff) << 16) | (u & 0xff00) | ((u >>> 16) & 0xff) | 0xff000000) >>> 0; },
    "playlist.isTrackMuteLock": (...a) => { arity(a, 1, 1); return !!pl(a[0]).lock; },
    "playlist.getTrackActivityLevelVis": (...a) => { arity(a, 1, 1); return F(pl(a[0]).act); },
    "playlist.getLiveLoopMode": (...a) => { arity(a, 1, 1); return pl(a[0]).loop; },
    "playlist.getLiveTriggerMode": (...a) => { arity(a, 1, 1); return pl(a[0]).trigMode; },
    "playlist.getLivePosSnap": (...a) => { arity(a, 1, 1); return pl(a[0]).posSnap; },
    "playlist.getLiveTrigSnap": (...a) => { arity(a, 1, 1); return pl(a[0]).trigSnap; },
    // 表の引数数は 1〜2 (C と同一・main #2927)。value -1 (省略を含む) は反転、それ以外は下位 1 byte を設定 (REPORT_PY61 §3)。準備判定 (-2) は未モデル
    // PY-102 (#2883): value 検査 (argI) を index の範囲検査より先に行う。C の dispatch は型を先に見るため (code 5 が先)
    "playlist.muteTrackLock": (...a) => { arity(a, 1, 2); const v = argI(a, 1, -1); if (!st.safeEdit) throw UNSAFE(); const t = pl(a[0]); t.lock = v === -1 ? (t.lock ? 0 : 1) : v & 0xff; },
    "ui.getVisible": (w) => !!st.windows[w],
    "ui.showWindow": (w) => { st.windows[w] = true; },
    "ui.hideWindow": (w) => { st.windows[w] = false; },
    // PY-95 (#2831): 状態 1 つを返すだけの ui ゲッター 9 件 (REPORT_PY95)。初期値は未実測の仮置き (provider/fl_engine.c と同じ)。
    // isMetronomeEnabled / isPrecountEnabled は general.getUseMetronome / getPrecount と同じ状態を読む
    "ui.isClosing": (...a) => { arity(a, 0, 0); return st.uiClosing; },
    "ui.getTimeDispMin": (...a) => { arity(a, 0, 0); return st.uiTimeDispMin; },
    "ui.isMetronomeEnabled": (...a) => { arity(a, 0, 0); return st.useMetronome; },
    "ui.isPrecountEnabled": (...a) => { arity(a, 0, 0); return st.precount; },
    "ui.isStartOnInputEnabled": (...a) => { arity(a, 0, 0); return st.uiStartOnInput; },
    "ui.isLoopRecEnabled": (...a) => { arity(a, 0, 0); return st.uiLoopRec; },
    "ui.getStepEditMode": (...a) => { arity(a, 0, 0); return st.uiStepEdit; },
    "ui.isBrowserAutoHide": (...a) => { arity(a, 0, 0); return st.uiBrowserAutoHide; },
    "ui.getSnapMode": (...a) => { arity(a, 0, 0); return st.uiSnapMode; },
    // PY-121 (#2982): PE で確定した引数書式 (PyArg fmt) と時間引数の頭打ち (0x7d0)。表示そのものは未モデルで、最後の時間引数だけ st.displayTime に残す
    "ui.crDisplayRect": (...a) => disp(a, 5, 6, 4),
    "ui.miDisplayRect": (...a) => disp(a, 3, 4, 2),
    "ui.miDisplayDockRect": (...a) => disp(a, 4, 4, 3),
    "ui.showNotification": (...a) => { arity(a, 1, 1); argI(a, 0, 0); },
    "ui.closeAllMenu": (...a) => { arity(a, 0, 0); },
    "ui.closeActivePopupMenu": (...a) => { arity(a, 0, 0); },
    // PY-133 (#3014): PE で PyArg 書式を確定した showPicker・openEventEditor (REPORT_PY133)。作用先は未モデルで、個数と型だけ検査して None
    "ui.showPicker": (...a) => { arity(a, 1, 2); argI(a, 0, 0); argI(a, 1, -1); },
    "ui.openEventEditor": (...a) => { arity(a, 2, 3); argI(a, 0, 0); argI(a, 1, 0); argI(a, 2, 0); },
    // PY-132 (#3013): toggleBrowserNode は PE の書式 '|i' (既定 -1)。値 -1/0/1 の分岐 (0xa89690 → 0xa26190 / 0xa07d00) だけを st.browserOp に残す (1 切替・2 閉じる・3 開く・0 なし)。
    // selectBrowserMenuItem・previewBrowserMenuItem は NOARGS。作用 (0xfdd2c0 のキー送出) は未モデル
    "ui.toggleBrowserNode": (...a) => { arity(a, 0, 1); const v = argI(a, 0, -1); st.browserOp = v === -1 ? 1 : v === 0 ? 2 : v === 1 ? 3 : 0; },
    "ui.selectBrowserMenuItem": (...a) => { arity(a, 0, 0); },
    "ui.previewBrowserMenuItem": (...a) => { arity(a, 0, 0); },
    // PY-119 (#2980): PE で呼出し経路を確定した ui ゲッター 6 件 (REPORT_PY119)。値は未実測の仮置き (provider/fl_engine.c と同じ)
    "ui.getFocused": (...a) => { arity(a, 1, 1); ix(a[0]); return false; },
    "ui.getFocusedFormID": (...a) => { arity(a, 0, 0); return 0; },
    "ui.getFocusedFormCaption": (...a) => { arity(a, 0, 0); return ""; },
    "ui.getFocusedPluginName": (...a) => { arity(a, 0, 0); return ""; },
    "ui.getHintMsg": (...a) => { arity(a, 0, 0); return ""; },
    "ui.isInPopupMenu": (...a) => { arity(a, 0, 0); return false; },
    // PY-129 (#3006): PE で呼出し経路を確定した ui setter 3 件 (REPORT_PY129)。状態は持たない (仮置き)。書込み先と書込み値の読出し経路は未確定。範囲外の挙動も未確認
    "ui.setHintMsg": (...a) => { arity(a, 1, 1); str(a[0]); },
    "ui.setFocused": (...a) => { arity(a, 1, 1); ix(a[0]); },
    "ui.setSnapMode": (...a) => { arity(a, 1, 1); const i = ix(a[0]); if (i < 0 || i > 14) throw RANGE(); },
    // PY-128 (#3005): getProgTitle は PE rodata の定数 (UTF-16)。getHintValue は状態を読まず、(int32)(value*100) / max を最近接偶数で整数化して "%" (REPORT_PY128)
    "ui.getProgTitle": (...a) => { arity(a, 0, 0); return "FL Studio 2026"; },
    "ui.getHintValue": (...a) => {
      arity(a, 2, 2);
      const v = pyInt(a[0]), m = pyInt(a[1]);
      const q = Math.imul(v, 100) / (m | 0);
      if (!(q >= -9223372036854775808 && q < 9223372036854775808)) return "-9223372036854775808%";
      const f = Math.floor(q), d = q - f;
      return `${d < 0.5 ? f : d > 0.5 ? f + 1 : f % 2 === 0 ? f : f + 1}%`;
    },
    // PY-130 (#3007): PE で書込み経路を確定した ui setter 2 件と getVersion (ui)。値は未実測の仮置き (provider/fl_engine.c と同じ・REPORT_PY130_3007)
    "ui.setBrowserAutoHide": (...a) => { arity(a, 1, 1); st.uiBrowserAutoHide = argI(a, 0, 0) === 1; },
    "ui.setStepEditMode": (...a) => { arity(a, 1, 1); st.uiStepEdit = argI(a, 0, 0) === 1; },
    // PY-236 (#3706): PE 0xd6cc60 は引数を読まず、gate 真なら byte [0x16bc9f2] を反転する (REPORT_PY236_3706)
    "ui.setTimeDispMin": (...a) => { arity(a, 0, 0); st.uiTimeDispMin = !st.uiTimeDispMin; },
    // mode 0..3 は int、4..6 は str、他は int 0 (PE 0xd6c2f0 の分岐表)。既定 mode 4 (|i)
    "ui.getVersion": (...a) => { arity(a, 0, 1); const m = argI(a, 0, 4); return m >= 4 && m <= 6 ? "" : 0; },
    // PY-246 (#3759): 送出キー 15 関数 (PE 0xfdd2c0 の leaf → 0x8186a0。REPORT_PY140)。戻り値は PY-141 で未確定の仮置き 0。送出の成否のゲートは PY-245 で未確定
    "ui.up": (...a) => { arity(a, 0, 1); sendKey(0x26, 0, argI(a, 0, 1)); return 0; },
    "ui.down": (...a) => { arity(a, 0, 1); sendKey(0x28, 0, argI(a, 0, 1)); return 0; },
    "ui.left": (...a) => { arity(a, 0, 1); sendKey(0x25, 0, argI(a, 0, 1)); return 0; },
    "ui.right": (...a) => { arity(a, 0, 1); sendKey(0x27, 0, argI(a, 0, 1)); return 0; },
    "ui.cut": (...a) => { arity(a, 0, 0); sendKey(0x58, 4, 1); return 0; },
    "ui.copy": (...a) => { arity(a, 0, 0); sendKey(0x43, 4, 1); return 0; },
    "ui.paste": (...a) => { arity(a, 0, 0); sendKey(0x56, 4, 1); return 0; },
    "ui.insert": (...a) => { arity(a, 0, 0); sendKey(0x2d, 0, 1); return 0; },
    "ui.delete": (...a) => { arity(a, 0, 0); sendKey(0x2e, 0, 1); return 0; },
    "ui.enter": (...a) => { arity(a, 0, 0); sendKey(0x0d, 0, 1); return 0; },
    "ui.escape": (...a) => { arity(a, 0, 0); sendKey(0x1b, 0, 1); return 0; },
    "ui.yes": (...a) => { arity(a, 0, 0); sendKey(0x59, 0, 1); return 0; },
    "ui.no": (...a) => { arity(a, 0, 0); sendKey(0x4e, 0, 1); return 0; },
    "ui.nextWindow": (...a) => { arity(a, 0, 0); sendKey(0x09, 0, 1); return 0; },
    // PE: arg > 0 で修飾 0 (Tab)、arg <= 0 で Shift (修飾 1) + Tab。stub の引数名 shift と符号が逆 (REPORT_PY140 の未解決)
    "ui.selectWindow": (...a) => { arity(a, 1, 1); sendKey(0x09, argI(a, 0, 0) > 0 ? 0 : 1, 1); return 0; },
    "plugins.isValid": (i, slot = -1) => (slot < 0 ? !!st.channels[i] : !!st.mixer[i]?.slots[slot]),
    "plugins.getPluginName": (i, slot = -1, userName) => (slot < 0 ? ch(i).plugin : (tr(i).slots[slot] ?? "")),
    "plugins.getParamCount": () => st.params.length,
    "plugins.getParamName": (p) => st.params[p]?.name ?? "",
    "plugins.getParamValue": (...a) => { arity(a, 2, 4); const [pv, q] = plugIn(a, 0, 4); return F(pv[q]); },
    "plugins.getParamValueString": (...a) => { arity(a, 2, 4); const [pv, q] = plugIn(a, 0, 4); return `${(pv[q] * 100).toFixed(1)} %`; },
    "plugins.setParamValue": (...a) => { arity(a, 3, 6); const x = argD(a, 0); const [pv, q] = plugIn(a, 1, 6); pv[q] = x; },
    // MIDI scripting (PY-6): device script が使う device.* の最小模擬。forwardMIDICC / midiOutMsg は呼出しを st.midiOut に記録する
    // general.getVersion = MIDI scripting API バージョン (int)。実機値は未実測のため固定のモック値 (同梱 script は print するだけ)
    "general.getVersion": (...a) => { arity(a, 0, 0); return st.scriptingVersion ?? 1; },
    // PY-87 (#2738): 状態 1 つを返すだけの 4 関数。初期値は未実測の仮置き (provider/fl_engine.c と同じ)
    "general.getChangedFlag": (...a) => { arity(a, 0, 0); return st.changedFlag; },
    "general.getUseMetronome": (...a) => { arity(a, 0, 0); return st.useMetronome; },
    "general.getPrecount": (...a) => { arity(a, 0, 0); return st.precount; },
    "general.getRecPPQ": (...a) => { arity(a, 0, 0); return st.recPPQ; },
    // PY-94 (#2830): 状態 1 つを返すだけの 7 関数 (REPORT_PY94)。値は未実測の仮置き (provider/fl_engine.c と同じ)
    "general.getUndoHistoryPos": (...a) => { arity(a, 0, 0); return st.undoPos; },
    "general.getUndoHistoryCount": (...a) => { arity(a, 0, 0); return st.undoCount; },
    "general.getUndoHistoryLast": (...a) => { arity(a, 0, 0); return st.undoLast; },
    "general.safeToEdit": (...a) => { arity(a, 0, 0); return st.safeEdit; },
    "general.getProjectTitle": (...a) => { arity(a, 0, 0); return st.projTitle; },
    "general.getProjectAuthor": (...a) => { arity(a, 0, 0); return st.projAuthor; },
    "general.getProjectGenre": (...a) => { arity(a, 0, 0); return st.projGenre; },
    // PY-120 (#2984): PE 0xd791b0 は obj.+0x50 の配列 (+0x3c0) の件数を返す。件数は実行時の状態のため仮置き 0 (REPORT_PY120_2984)
    "launchMapPages.length": (...a) => { arity(a, 0, 0); return st.launchPages; },
    // PY-138 (#3029): PE init 0xd79020 (書式 sii)・updateMap 0xd79290 (i)・createOverlayMap 0xd7a130 (iiii) は引数書式と成功時の戻り (None) を確定。page 配列への副作用は未確定のため状態を変えない (REPORT_PY138)
    "launchMapPages.init": (...a) => { arity(a, 3, 3); str(a[0]); argI(a, 1, 0); argI(a, 2, 0); },
    "launchMapPages.updateMap": (...a) => { arity(a, 1, 1); argI(a, 0, 0); },
    "launchMapPages.createOverlayMap": (...a) => { arity(a, 4, 4); for (let i = 0; i < 4; i++) argI(a, i, 0); },
    // PY-243 (#3745): PE 0xd7a3a0 は書式 iii (0xd7a3d8)・成功時の戻り [0x16b82e0] = _Py_NoneStruct (None、REPORT_PY243)。項目書込み (0xd7a280) は項目の状態を持たないため状態を変えない
    "launchMapPages.setMapItemTarget": (...a) => { arity(a, 3, 3); for (let i = 0; i < 3; i++) argI(a, i, 0); },
    // PY-125 (#3001): PE 0xd6a1f0 (clearLog) と 0xd6a060 (dumpScoreLog) は、成功経路 (述語 P 真・gate 真) で dispatch 0xd843d0 を経て None を返す (REPORT_PY125 §4)。効果は API から観測できないため状態を持たない
    "general.clearLog": (...a) => { arity(a, 0, 0); return undefined; },
    "general.dumpScoreLog": (...a) => { arity(a, 1, 2); argI(a, 0, 0); argI(a, 1, 0); return undefined; },
    // PY-235 (#3701): 成功経路 (gate 0 を仮定) は戻り値 = value (int32)。他の family は未確定のため code 2 (C provider と同じ未実装 error)
    "general.processRECEvent": (...a) => { arity(a, 3, 3); const e = ix(a[0]) >>> 0; const v = ix(a[1]) | 0; const f = ix(a[2]); if (!recPassFamily(e, f)) throw new FlError("Unspecified error (not implemented: general.processRECEvent)", 2); return v; },
    // PY-96 (#2832): 選択範囲の読出し 4 件。PE 0xd786e0/0xd78700/0xd78500 は obj+0xd74 (start)・obj+0xd78 (end) を読み、
    // 0xd78720 は 0xe43e80 (start>=0 かつ end>=0) を bool で返す。未選択は負値。初期値 -1 は未実測の仮置き (provider/fl_engine.c と同じ)
    "arrangement.selectionStart": (...a) => { arity(a, 0, 0); return st.selStart; },
    "arrangement.selectionEnd": (...a) => { arity(a, 0, 0); return st.selEnd; },
    "arrangement.liveSelectionStart": (...a) => { arity(a, 0, 0); return st.selStart; },
    "arrangement.selectionIsActive": (...a) => { arity(a, 0, 0); return st.selStart >= 0 && st.selEnd >= 0; },
    // PY-152 (#2983): 呼出し構造と PyArg 書式は PE で確定 (currentTime 'i'・selectionSet 'ii|iii'・liveSelection 'ii'・addAutoTimeMarker 'is'・jumpToMarker 'i|i')。個数は fl_table (必須 2) に合わせた暫定で、jumpToMarker は PE (必須 1) と不一致 (REPORT_PY152 未解決)。
    // 選択の 2 件は selSet (PE 0xe43d30 の規則) で selStart/selEnd を変える (PY-144 #3043)。マーカー・liveSelection・jumpToMarker の 3 件は副作用が未同定のため状態を変えない。currentTime は仮置きの状態 arrTime (0) を返す (provider/fl_engine.c と同じ)
    "arrangement.currentTime": (...a) => { arity(a, 1, 1); argI(a, 0, 0); return st.arrTime; },
    "arrangement.selectionClear": (...a) => { arity(a, 0, 0); selSet(-1, -1); },
    "arrangement.selectionSet": (...a) => { arity(a, 2, 5); const x = argI(a, 0, 0), y = argI(a, 1, 0); for (let i = 2; i < 5; i++) argI(a, i, 0); selSet(x, y); },
    "arrangement.liveSelection": (...a) => { arity(a, 2, 2); liveSel(argI(a, 0, 0), argI(a, 1, 0)); },
    "arrangement.addAutoTimeMarker": (...a) => { arity(a, 2, 2); argI(a, 0, 0); str(a[1]); },
    "arrangement.jumpToMarker": (...a) => { arity(a, 2, 2); argI(a, 0, 0); argI(a, 1, 0); },
    // PY-143 (#3041): PE 0xd78030 (getMarkerName) と 0xd785a0 (currentTimeHint) の呼出し構造と戻り str は REPORT_PY143 で確定。
    // マーカー表は件数 0 の仮置き (addAutoTimeMarker の副作用は未同定で登録しない)。範囲外は空文字 (PE 0x1063810 の範囲外経路)。
    // currentTimeHint の BBT 分解 (PE 0x1312080) は未同定のため、PPQ 96・4 拍子の仮置きで bar:beat:tick を返す (provider/fl_engine.c と同じ)。
    "arrangement.getMarkerName": (...a) => { arity(a, 1, 1); argI(a, 0, 0); return ""; },
    "arrangement.currentTimeHint": (...a) => {
      arity(a, 2, 4); argI(a, 0, 0); const t = argI(a, 1, 0); argI(a, 2, st.recPPQ);
      const zeroBased = argI(a, 3, 0) === 1, per = 4 * 96;
      const bar = Math.trunc(t / per), beat = Math.trunc((t % per) / 96), tick = t % 96;
      return `${bar + (zeroBased ? 0 : 1)}:${beat + (zeroBased ? 0 : 1)}:${tick}`;
    },
    // PY-172 (#3219): PE 0xd67000 は件数 (配列 null で 0)、0xd67030 は索引 [0, 件数-1] の外を status -4。件数 0 は仮置き (provider/fl_engine.c の PGRP_N と同じ)
    "patterns.getPatternGroupCount": (...a) => { arity(a, 0, 0); return PGRP_N; },
    "patterns.getPatternGroupName": (...a) => { arity(a, 1, 1); const i = argI(a, 0, 0); if (i < 0 || i >= PGRP_N) throw RANGE(); return ""; },
    // PY-180 (#3278): .data の初期値 -1 (番兵)。書込み元は未特定 (REPORT_PY180)
    "patterns.getActivePatternGroup": (...a) => { arity(a, 0, 0); return -1; },
    "patterns.patternCount": (...a) => { arity(a, 0, 0); return PAT_N; },
    "patterns.patternNumber": (...a) => { arity(a, 0, 0); return PAT_NUMBER; },
    "patterns.isPatternDefault": (...a) => { arity(a, 1, 1); const i = argI(a, 0, 0); if (i < 1 || i > PAT_N) throw RANGE(); return false; },
    "patterns.isPatternSelected": (...a) => { arity(a, 1, 1); argI(a, 0, 0); return false; },
    // PY-119 (#2977): PE の setRecPPQ 0xd69350・setNumerator 0xd694e0・setDenominator 0xd69670 の範囲判定 (範囲外は status -3 Range error)。ゲート (safeToEdit 相当) は未確定のため真と仮定 (REPORT_PY119_2977)
    "general.setRecPPQ": (...a) => { arity(a, 1, 1); const v = ix(a[0]); if (v < 24 || v > 960) throw RANGE("Range error"); st.recPPQ = v; },
    "general.setNumerator": (...a) => { arity(a, 1, 1); const v = ix(a[0]); if (v < 1 || v > 16) throw RANGE("Range error"); st.numerator = v; },
    "general.setDenominator": (...a) => { arity(a, 1, 1); const v = ix(a[0]); if (v < 2 || v > 16) throw RANGE("Range error"); st.denominator = v; },
    // undo 3 件は PE 0xd69af0 (共有コールバック) が範囲検査なしに値を書く (kind 0=Pos・1=Count・2=Last)。ゲートは上と同じく仮に真。getter と同じ状態を書く
    "general.setUndoHistoryPos": (...a) => { arity(a, 1, 1); st.undoPos = ix(a[0]); },
    "general.setUndoHistoryCount": (...a) => { arity(a, 1, 1); st.undoCount = ix(a[0]); },
    "general.setUndoHistoryLast": (...a) => { arity(a, 1, 1); st.undoLast = ix(a[0]); },
    // PY-121 (#2985): screen 状態の 5 関数 (PE 0xd7c7e0・0xd7c830・0xd7c880・0xd7c8c0・0xd7c740)。初期値は未実測の仮置き (provider/fl_engine.c と同じ)
    "screen.isBlanked": (...a) => { arity(a, 0, 0); return st.screenBlanked; },
    "screen.isUnBlank": (...a) => { arity(a, 0, 0); return st.screenUnBlank; },
    "screen.getScreenActiveCounter": (...a) => { arity(a, 0, 0); return st.screenActiveCounter; },
    "screen.setScreenActiveCounter": (...a) => { arity(a, 1, 1); st.screenActiveCounter = (st.screenActiveCounter + argI(a, 0, 0)) | 0; },
    "screen.unBlank": (...a) => { arity(a, 1, 1); st.screenUnBlank = argI(a, 0, 0) === 1; },
    // PY-135 (#3022): 描画・メーター系 6 件 (PE 0xd7ada0・0xd7b690・0xd7ae80・0xd7af40・0xd7bcb0・0xd7bec0)。addMeter 以外は引数検査と None だけを模す (REPORT_PY135)。
    // addMeter は書式解析が成功 (rc>0) かつ scr≠0 のとき PE 0xd7d9e0 が isUnBlank (scr+0x1d1) を真にし、activeCounter を scr+0x1dc (仮置き 0) にする。解析失敗は状態を変えない
    "screen.addMeter": (...a) => { arity(a, 4, 5); for (let i = 0; i < 4; i++) argI(a, i, 0); argI(a, 4, 0); st.screenUnBlank = true; st.screenActiveCounter = st.screenDefaultCounter; },
    // addTextLine (#5328): 書式 siiii (必須 5)。成功経路で scr≠0 のとき PE 0xd7d460 の副作用 scr+0x1cc←scr+0x1dc・scr+0x1d1←1 を模す。
    // 行 record ([scr+0x1c4] の末尾への書込み) の中身は未確定のため模さない (REPORT_PY5328)
    "screen.addTextLine": (...a) => { arity(a, 5, 5); str(a[0]); for (let i = 1; i < 5; i++) argI(a, i, 0); if (st.screenAlive) { st.screenActiveCounter = st.screenDefaultCounter; st.screenUnBlank = true; } },
    "screen.displayBar": (...a) => { arity(a, 5, 5); argI(a, 0, 0); argI(a, 1, 0); str(a[2]); argF(a, 3); argI(a, 4, 0); },
    "screen.fillRect": (...a) => { arity(a, 5, 5); for (let i = 0; i < 5; i++) argI(a, i, 0); },
    "screen.drawRect": (...a) => { arity(a, 5, 5); for (let i = 0; i < 5; i++) argI(a, i, 0); },
    "screen.drawText": (...a) => { arity(a, 6, 6); argI(a, 0, 0); str(a[1]); for (let i = 2; i < 6; i++) argI(a, i, 0); },
    "screen.eraseRect": (...a) => { arity(a, 4, 4); for (let i = 0; i < 4; i++) argI(a, i, 0); },
    // blank (PE 0xd7c600 → callback 0xd7c5a0 → 0xd7d110): 第 1 引数が 1 なら isBlanked (scr+0x1d0) を真に書く。真→偽の解除では activeCounter を scr+0x1dc から戻す (初期値は未実測の仮置き 0)
    "screen.blank": (...a) => { arity(a, 2, 2); const b = argI(a, 0, 0) === 1; argI(a, 1, 0); if (b !== st.screenBlanked) { if (!b) st.screenActiveCounter = st.screenDefaultCounter; st.screenBlanked = b; } },
    // PY-136 (#3025): screen 初期化・メニュー系 10 件 (PE 0xd7aa40・0xd7ab00・0xd7b0a0・0xd7b000・0xd7ccb0・0xd7b1f0・0xd7b170・0xd7c9a0・0xd7cac0・0xd7cbe0)。scr 未生成の経路は PE で AV のため Unspecified error を仮置き。引数名と意味は未確定 (REPORT_PY136)
    "screen.init": (...a) => { arity(a, 6, 6); for (let i = 0; i < 6; i++) argI(a, i, 0); Object.assign(st, { screenAlive: true, screenDirty: false, screenMenuShowing: false, screenSetup: { l: 0, t: [30, 10, 10, 2, 4000] } }); },
    "screen.setup": (...a) => { arity(a, 6, 6); const v = Array.from({ length: 6 }, (_, i) => argI(a, i, 0)); scrNeed(); st.screenSetup = { l: v[0], t: v.slice(1) }; },
    "screen.update": (...a) => { arity(a, 0, 0); if (st.screenAlive) st.screenDirty = false; },
    "screen.deInit": (...a) => { arity(a, 0, 0); Object.assign(st, { screenAlive: false, screenDirty: false, screenMenuShowing: false }); },
    "screen.keepDisplayActive": (...a) => { arity(a, 0, 0); if (st.screenAlive) st.screenDirty = true; },
    "screen.hideMenu": (...a) => { arity(a, 0, 0); scrNeed(); st.screenMenuShowing = false; },
    "screen.menuShowing": (...a) => { arity(a, 0, 0); scrNeed(); return st.screenMenuShowing; },
    "screen.menuItemClick": (...a) => { arity(a, 0, 0); },
    "screen.menuNext": (...a) => { arity(a, 0, 0); },
    "screen.menuPrev": (...a) => { arity(a, 0, 0); },
    "device.getPortNumber": () => st.devicePort ?? 0,
    "device.isAssigned": () => true,
    "device.setHasMeters": () => { st.hasMeters = true; },
    // PY-231 (#3671): PE 0xd75120 (書式 "L|i"・既定 1 は PE が書く)。判定順 (-7 → -6) は midiOutMsg と同じ判定順と仮置き (REPORT_PY231 §1b)。送るのは第 1 引数の word。mode は stub 名 (PE の kwlist 名は forwardTo・REPORT_PY231 §1)
    // PY-276 (#3949): PE 0xfdc8a0 は添字の値が変わったときだけ送る。C (fl_engine.c) と同じく未設定 (-1) から始め、範囲外の添字は重複検出せず送る
    // message 欠落は C の既定 0 と同じ (JS の TypeError にしない)
    "device.forwardMIDICC": (message = 0, mode = 1) => {
      if (!st.devAssigned) throw new FlError("Device not assigned", 7);
      if (!st.linkAssigned) throw new FlError("Linked device not assigned", 6);
      const w = Number(BigInt.asUintN(32, BigInt(message)));
      const i = ix(mode);
      if (i < 0 || i >= FCC_N) { st.midiOut.push({ api: "forwardMIDICC", message, mode }); return; }
      if (st.fccLast[i] === w) return;
      st.fccLast[i] = w;
      st.midiOut.push({ api: "forwardMIDICC", message, mode });
    },
    // PY-227 (#3655): PE 0xd747f0 と同じ順 (引数 → -7 → -6)。channel ≤ -1 は message の下位 32bit、channel ≥ 0 は arg4 を bit 24–31 に入れた word を記録する
    "device.midiOutMsg": (...a) => {
      const msg = argI(a, 0, 0), ch = argI(a, 1, -1), d1 = argI(a, 2, 0), d2 = argI(a, 3, 0), a4 = argI(a, 4, 0);
      if (!st.devAssigned) throw new FlError("Device not assigned", 7);
      if (!st.linkAssigned) throw new FlError("Linked device not assigned", 6);
      const word = ch >= 0 ? (((ch & 0xf) | msg) + (d1 << 8) + (d2 << 16) + (a4 << 24)) >>> 0 : msg >>> 0;
      st.midiOut.push({ api: "midiOutMsg", args: a, word });
    },
    // PY-215 (#3568): PE 0xd75d30 と同じ (-1 → -1、連動表が空の index ≥ 0 → None)。表の供給元は仮置き (空)。device・link の割当は見ない
    "device.getLinkedChannel": (...a) => { arity(a, 1, 1); const i = argI(a, 0, 0); if (i === -1) return -1; return undefined; },
    // PY-4846 (#3568 子 B): index == -1 の経路だけ PE 確定 (REPORT_PY215 §1)。index >= 0 は未確定のため C provider と同じ未実装 error (code 2)
    "device.getLinkedValue": (...a) => { arity(a, 1, 1); const i = argI(a, 0, 0); if (i === -1) return -1; throw new FlError("Unspecified error (not implemented: device.getLinkedValue index>=0)", 2); },
    "device.getLinkedInfo": (...a) => { arity(a, 1, 1); const i = argI(a, 0, 0); if (i === -1) return -1; throw new FlError("Unspecified error (not implemented: device.getLinkedInfo index>=0)", 2); },
    "device.getLinkedParamName": (...a) => { arity(a, 1, 1); const i = argI(a, 0, 0); if (i === -1) throw new FlError("Plugin not valid", 8); throw new FlError("Unspecified error (not implemented: device.getLinkedParamName index>=0)", 2); },
    "device.getLinkedValueString": (...a) => { arity(a, 1, 1); const i = argI(a, 0, 0); if (i === -1) throw new FlError("Plugin not valid", 8); throw new FlError("Unspecified error (not implemented: device.getLinkedValueString index>=0)", 2); },
    // PY-260 (#3840) / PY-390 (#4830): PE 0xd75b60 (書式 "i|i")。表 0x16bacb8 は供給元未確定のため空と仮定し、未発見の -1 を返す。device・link の割当は見ない (C provider と同じ)
    "device.findEventID": (...a) => { arity(a, 1, 2); argI(a, 0, 0); argI(a, 1, 0); return -1; },
    // PY-260 (#3840) / PY-390 (#4830): PE 0xd76060 (書式 "i")。device 無しは -7 (PE 確定・準備判定は真と仮定)。device 有りの値は未確定のため C provider と同じ未実装 error (code 2)
    "device.isDoubleClick": (...a) => {
      arity(a, 1, 1); argI(a, 0, 0);
      if (!st.devAssigned) throw new FlError("Device not assigned", 7);
      throw new FlError("Unspecified error (not implemented: device.isDoubleClick assigned)", 2);
    },
    // PY-206 (#3494): PE 0xd75f40・0xd75f80・0xd75fc0 は assigned 機器 (obj.+0x50) の vtbl 先を呼び、戻り status 0 で None を返す (REPORT_PY206)。vtbl 先の効果は未読のため状態を持たない
    "device.createRefreshThread": (...a) => { arity(a, 0, 0); },
    "device.destroyRefreshThread": (...a) => { arity(a, 0, 0); },
    "device.fullRefresh": (...a) => { arity(a, 0, 0); },
    // PY-206: PE 0xd76980 (float32 obj.+0x3d0)・0xd75a40 (bool)・0xd76b80 (bool byte +0x48) の状態読出し。初期値は未実測の仮置き (provider/fl_engine.c と同じ)
    "device.getIdleElapsed": (...a) => { arity(a, 0, 0); return st.idleElapsed; },
    "device.isMidiOutAssigned": (...a) => { arity(a, 0, 0); return st.midiOutAssigned; },
    "device.getMasterSync": (...a) => { arity(a, 0, 0); return st.masterSync; },
    // PY-206: PE 0xd76a60 の setter callback 0xd769c0 は obj.+0x50 の機器の [+0x7c]+0x48 に (value == 1) を書く (getMasterSync と同じ byte)。述語 P は真と仮定 (REPORT_PY125 と同じ仮定)
    "device.setMasterSync": (...a) => { arity(a, 1, 1); st.masterSync = argI(a, 0, 0) === 1; },
    ...createIlmcp(st, {
      RANGE,
      INVALID: (m) => new FlError(m, 1),
      makeChannel: (plugin) => ({ name: plugin, plugin, vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: false, fx: 0, steps: new Array(64).fill(0), pitchN: 2, pv: [...PARAM_DEFAULT] }),
      nMixer: st.mixer.length,
    }),
  };

  const record = [];
  return {
    state: st,
    record,
    call(name, args) {
      record.push([name, args]);
      const f = impl[name];
      if (!f) return null; // 未実装 API は None を返す (PoC)
      // 引数の None は省略 (undefined) と同じ扱い。provider (fl_dispatch.c: tag 'N' = 既定値) と揃える
      return f(...args.map((a) => (a === null ? undefined : a)));
    },
    implemented: () => Object.keys(impl),
    setSafeEdit: (v) => { st.safeEdit = !!v; },
    stepItemProbe: (prm, value, seed0, seed1) => {
      const a = newItem(), b = newItem();
      itemWrite(a, prm, 0, seed0); itemWrite(b, prm, 0, seed1);
      itemsSet([a, b], prm, value);
      return itemGet(b, prm);
    },
    noteEnumProbe: (seed, n, chan, step, V) => noteEnum(noteGen(seed, n), chan, step, V),
    noteEnumNotes: (notes, chan, step, V) => noteEnum(notes.map(([d0, len, ch]) => ({ ...newItem(), d0, len, ch })), chan, step, V),
    // PY-224 (#3628): 検査用に loop 行 T[1] を置く。recs は [cid, f4, len] の列 (fl_provider.mjs の setLoop と同じ)
    setLoop: (row, flag49e, flag54, recs) => {
      if (recs.length > LOOP_MAX) throw new Error("loop record 超過 (上限 8)");
      st.loop = { row: !!row, flag49e: !!flag49e, flag54: !!flag54, recs: recs.map(([cid, f4, len]) => ({ cid, f4, len })) };
    },
    gridItemsProbe: (seed, n) => { st.gridItems = gridGen(seed, n); return st.gridItems.length; },
    // PY-246 (#3759): 送出キーの記録の読出し口 (C の fl_engine_key_* と同じ)。f: 0 = vk・1 = 修飾・2 = 回数
    keyClear: () => { st.keys = []; },
    keyN: () => st.keys.length,
    keyGet: (i, f) => { const k = st.keys[i]; return k ? [k.vk, k.mod, k.count][f] : -1; },
  };
}
