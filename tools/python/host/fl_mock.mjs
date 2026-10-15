// FLEngine 模擬ホスト (PoC)。実装版では FLEngine wasm の export に置換される同一インタフェース:
//   engine.call("mixer.getTrackName", [index, ...]) -> any
// 返す number は整数なら int、実数なら float になる。整数値の float は F(x) で明示。
import { createIlmcp } from "./ilmcp.mjs";
const F = (v) => ({ t: "D", v });
// PY-100 (#2879): PE 0xd5b930 の readout (C provider と同一)。構造体 = grid bit が立つ step。param 0..7 の既定値は stub 順、範囲外と param 8 (未モデル) は -1
const STEP_DEF = [60, 100, 64, 120, 64, 64, 64, 0];
const stepParam = (k, pos, prm) => (pos < 0 || pos >= 64 || !k.steps[pos] || prm < 0 || prm > 7 ? -1 : STEP_DEF[prm]);

class FlError extends Error {
  constructor(msg, code) { super(msg); this.flCode = code; }
}
const RANGE = (m) => new FlError(m || "Index out of range", 4);
// PY-76 (#2563): cvtsd2si (64bit・最近接偶数丸め)。範囲外と inf は 0x8000000000000000 (INT64_MIN) (REPORT_PY72 §callback unit 2)
const cvtSi64 = (x) => {
  if (!(x >= -(2 ** 63) && x < 2 ** 63)) return -(2 ** 63);
  const f = Math.floor(x), d = x - f;
  return d < 0.5 ? f : d > 0.5 ? f + 1 : (f % 2 === 0 ? f : f + 1);
};
const WRONG = (m) => new FlError(m || "Wrong number of function parameters or wrong parameter type", 5);
// mixer の色の R/B 入替え (REPORT_PY115.md §2)。既定色は FL の .bss 0x15f6774 の初期値 (REPORT_PY118)
const swapRb = (v) => ((v & 0xff) << 16) | (v & 0xff00) | ((v >>> 16) & 0xff);
const MIX_DEFAULT_COLOR = 0xff636c71;
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

export function createMockEngine() {
  const st = {
    tempo: 130,
    playing: false,
    changedFlag: 0, useMetronome: false, precount: false, recPPQ: 96,
    launchPages: 0,
    uiClosing: false, uiTimeDispMin: false, uiStartOnInput: false, uiLoopRec: false, uiStepEdit: false, uiBrowserAutoHide: false, uiSnapMode: 0,
    undoPos: 0, undoCount: 0, undoLast: 0, safeEdit: true, projTitle: "", projAuthor: "", projGenre: "",
    selStart: -1, selEnd: -1,
    arrTime: 0,
    numerator: 4, denominator: 4,
    screenBlanked: false, screenUnBlank: false, screenActiveCounter: 0,
    selectedChannel: 0,
    channels: [
      { name: "Kick", plugin: "Sampler", vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: true, fx: 1, steps: new Array(64).fill(0), pitchN: 2 },
      { name: "Snare", plugin: "Sampler", vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: false, fx: 2, steps: new Array(64).fill(0), pitchN: 2 },
      { name: "3x Osc", plugin: "3x Osc", vol: 0.5, pan: 0.25, mute: false, solo: false, color: 0x7C5A6B, sel: false, fx: 0, steps: new Array(64).fill(0), pitchN: 2 },
    ],
    mixer: Array.from({ length: 127 }, (_, i) => ({
      name: i === 0 ? "Master" : i === 125 ? "Current" : `Insert ${i}`, vol: 0.8, pan: 0, mute: false, solo: false,
      color: 0, colorSet: false, sel: i === 0, slots: [], routes: i === 0 ? {} : { 0: 1.0 },
    })),
    playlist: Array.from({ length: 500 }, (_, i) => ({ name: `Track ${i + 1}`, color: 0x485156, lock: 0 })),
    windows: { 0: true, 1: false, 2: true, 3: false, 4: true, 5: false },
    displayTime: 0,
    params: [{ name: "Cutoff", v: 0.5 }, { name: "Resonance", v: 0.2 }, { name: "Gain", v: 0.8 }],
    prScripts: {},
    midiOut: [],
    log: [],
  };
  // channels / playlist の index は整数のみ (C provider の A_INT と同じ: 文字列・None・非整数は code 5)、範囲外は code 4
  const ix = (i) => { if (i === undefined) return 0; if (typeof i === "boolean") return +i; if (!Number.isInteger(i)) throw WRONG(); return i; };
  const str = (s) => { if (typeof s !== "string") throw WRONG(); return s; };
  const ch = (i) => { i = ix(i); if (!st.channels[i]) throw RANGE(); return st.channels[i]; };
  const pl = (i) => { i = ix(i); if (i < 1 || i > st.playlist.length) throw RANGE(); return st.playlist[i - 1]; };
  const tr = (i) => { if (!st.mixer[i]) throw RANGE(); return st.mixer[i]; };
  const tog = (cur, v) => (v === undefined || v === -1 ? !cur : !!v);
  // fl_provider の引数検査 (fl_dispatch.c type_ok / fl_a_int) と同じ: None は既定値、bool と整数のみ可、他は code 5
  const argI = (a, i, def) => {
    const v = a[i];
    if (i >= a.length || v === undefined) return def;
    if (typeof v === "boolean") return +v;
    if (Number.isInteger(v)) return v;
    throw WRONG();
  };
  const arity = (a, lo, hi) => { if (a.length < lo || a.length > hi) throw WRONG(); };
  // float 引数 (fl_a_dbl と同じ: None は 0、bool・整数・実数は可、他は code 5)。PE の書式 'f' は float32 に丸める
  const argF = (a, i) => { const v = a[i]; if (i >= a.length || v === undefined) return 0; if (typeof v === "boolean") return +v; if (typeof v === "number") return Math.fround(v); throw WRONG(); };
  const disp = (a, lo, hi, ti) => { arity(a, lo, hi); const v = Array.from({ length: hi }, (_, i) => argI(a, i, 0)); st.displayTime = Math.min(v[ti], 0x7d0); };

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
      argI(a, 3, 0); argI(a, 4, 0);
      if (stride < 1) throw RANGE();
      let p = offset;
      if (p < 0) { p = offset % stride; if (p < 0) p += stride; }
      for (; p < 64; p += stride) ch(ci).steps[p] = 1;
    },
    "channels.getChannelName": (i) => ch(i).name,
    "channels.setChannelName": (i, n) => { ch(i).name = str(n); },
    "channels.isChannelSelected": (i) => ch(i).sel,
    // PY-41 (#1514): 公開 stub の戻り型と説明で決めた 5 関数 (C provider と同一)。useGlobalIndex は未モデル
    "channels.isChannelMuted": (...a) => { arity(a, 1, 2); argI(a, 1, 0); return ch(a[0]).mute; },
    "channels.isChannelSolo": (...a) => { arity(a, 1, 2); argI(a, 1, 0); return ch(a[0]).solo; },
    "channels.getChannelColor": (...a) => { arity(a, 1, 2); argI(a, 1, 0); return ch(a[0]).color; },
    // PY-101 (#2878): PE 0xd5b420 は position<0 を 0 として返す (エラーにしない)。範囲外は index の -4 のみ (C と同一)
    "channels.getGridBit": (...a) => {
      arity(a, 2, 3);
      ix(a[0]); const p = ix(a[1]); argI(a, 2, 0);
      const k = ch(a[0]);
      if (p >= 64) throw RANGE();
      return p >= 0 && !!k.steps[p];
    },
    // PY-101 (#2878): PE 0xd5b360 は grid (+0x7ac) 非 null で True。mock の channel は生成時に grid を持つものとして扱い、null 経路は持たない (C と同一)
    "channels.isGridBitAssigned": (...a) => {
      arity(a, 1, 2);
      ix(a[0]); argI(a, 1, 0);
      ch(a[0]);
      return true;
    },
    // PY-101 (#2878): PE 0xd5bc10 → 0x12d3ff0。loop 分岐は未モデル (G1・G2・行テーブルの意味が未確定・#2932)。base 0x12d3e20 と同じ読出し
    "channels.getGridBitWithLoop": (...a) => {
      arity(a, 2, 3);
      ix(a[0]); const p = ix(a[1]); argI(a, 2, 0);
      const k = ch(a[0]);
      if (p >= 64) throw RANGE();
      return p >= 0 && !!k.steps[p];
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
    "channels.soloChannel": (i) => { ch(i).solo = !ch(i).solo; },
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
    },
    "channels.quickQuantize": (i) => { ch(i); },
    "channels.showEditor": (i) => { ch(i); },
    "mixer.trackCount": () => st.mixer.length,
    "mixer.getTrackName": (i) => tr(i).name,
    "mixer.setTrackName": (i, n) => { tr(i).name = n; },
    "mixer.getTrackVolume": (i, mode) => F(mode ? 20 * Math.log10(Math.max(tr(i).vol, 1e-6) / 0.8) : tr(i).vol),
    "mixer.setTrackVolume": (i, v) => { tr(i).vol = v; },
    "mixer.getTrackPan": (i) => F(tr(i).pan),
    "mixer.setTrackPan": (i, v) => { tr(i).pan = v; },
    "mixer.setTrackColor": (i, c) => { const t = tr(i); t.color = (swapRb(c) | 0xff000000) >>> 0; t.colorSet = true; },
    "mixer.getTrackColor": (i) => { const t = tr(i); return (swapRb(t.colorSet ? t.color : swapRb(MIX_DEFAULT_COLOR)) | 0xff000000) >>> 0; },
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
    // PY-102 (#2883): value 検査 (argI) を index の範囲検査より先に行う。C の dispatch は型を先に見るため (code 5 が先)
    "playlist.muteTrackLock": (...a) => { arity(a, 1, 2); const v = argI(a, 1, -1); const t = pl(a[0]); t.lock = v === -1 ? (t.lock ? 0 : 1) : v & 0xff; },
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
    // PY-119 (#2980): PE で呼出し経路を確定した ui ゲッター 6 件 (REPORT_PY119)。値は未実測の仮置き (provider/fl_engine.c と同じ)
    "ui.getFocused": (...a) => { arity(a, 1, 1); ix(a[0]); return false; },
    "ui.getFocusedFormID": (...a) => { arity(a, 0, 0); return 0; },
    "ui.getFocusedFormCaption": (...a) => { arity(a, 0, 0); return ""; },
    "ui.getFocusedPluginName": (...a) => { arity(a, 0, 0); return ""; },
    "ui.getHintMsg": (...a) => { arity(a, 0, 0); return ""; },
    "ui.isInPopupMenu": (...a) => { arity(a, 0, 0); return false; },
    "plugins.isValid": (i, slot = -1) => (slot < 0 ? !!st.channels[i] : !!st.mixer[i]?.slots[slot]),
    "plugins.getPluginName": (i, slot = -1, userName) => (slot < 0 ? ch(i).plugin : (tr(i).slots[slot] ?? "")),
    "plugins.getParamCount": () => st.params.length,
    "plugins.getParamName": (p) => st.params[p]?.name ?? "",
    "plugins.getParamValue": (p) => F(st.params[p].v),
    "plugins.getParamValueString": (p) => `${(st.params[p].v * 100).toFixed(1)} %`,
    "plugins.setParamValue": (v, p) => { st.params[p].v = v; },
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
    // PY-125 (#3001): PE 0xd6a1f0 (clearLog) と 0xd6a060 (dumpScoreLog) は、成功経路 (述語 P 真・gate 真) で dispatch 0xd843d0 を経て None を返す (REPORT_PY125 §4)。効果は API から観測できないため状態を持たない
    "general.clearLog": (...a) => { arity(a, 0, 0); return undefined; },
    "general.dumpScoreLog": (...a) => { arity(a, 1, 2); argI(a, 0, 0); argI(a, 1, 0); return undefined; },
    // PY-96 (#2832): 選択範囲の読出し 4 件。PE 0xd786e0/0xd78700/0xd78500 は obj+0xd74 (start)・obj+0xd78 (end) を読み、
    // 0xd78720 は 0xe43e80 (start>=0 かつ end>=0) を bool で返す。未選択は負値。初期値 -1 は未実測の仮置き (provider/fl_engine.c と同じ)
    "arrangement.selectionStart": (...a) => { arity(a, 0, 0); return st.selStart; },
    "arrangement.selectionEnd": (...a) => { arity(a, 0, 0); return st.selEnd; },
    "arrangement.liveSelectionStart": (...a) => { arity(a, 0, 0); return st.selStart; },
    "arrangement.selectionIsActive": (...a) => { arity(a, 0, 0); return st.selStart >= 0 && st.selEnd >= 0; },
    // PY-152 (#2983): 呼出し構造と PyArg 書式は PE で確定 (currentTime 'i'・selectionSet 'ii|iii'・liveSelection 'ii'・addAutoTimeMarker 'is'・jumpToMarker 'i|i')。個数は fl_table (必須 2) に合わせた暫定で、jumpToMarker は PE (必須 1) と不一致 (REPORT_PY152 未解決)。
    // 選択・マーカーの 5 件は副作用が未同定のため状態を変えない。currentTime は仮置きの状態 arrTime (0) を返す (provider/fl_engine.c と同じ)
    "arrangement.currentTime": (...a) => { arity(a, 1, 1); argI(a, 0, 0); return st.arrTime; },
    "arrangement.selectionClear": (...a) => { arity(a, 0, 0); },
    "arrangement.selectionSet": (...a) => { arity(a, 2, 5); for (let i = 0; i < 5; i++) argI(a, i, 0); },
    "arrangement.liveSelection": (...a) => { arity(a, 2, 2); argI(a, 0, 0); argI(a, 1, 0); },
    "arrangement.addAutoTimeMarker": (...a) => { arity(a, 2, 2); argI(a, 0, 0); str(a[1]); },
    "arrangement.jumpToMarker": (...a) => { arity(a, 2, 2); argI(a, 0, 0); argI(a, 1, 0); },
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
    "device.getPortNumber": () => st.devicePort ?? 0,
    "device.isAssigned": () => true,
    "device.setHasMeters": () => { st.hasMeters = true; },
    "device.forwardMIDICC": (message, mode = 1) => { st.midiOut.push({ api: "forwardMIDICC", message, mode }); },
    "device.midiOutMsg": (...a) => { st.midiOut.push({ api: "midiOutMsg", args: a }); },
    ...createIlmcp(st, {
      RANGE,
      INVALID: (m) => new FlError(m, 1),
      makeChannel: (plugin) => ({ name: plugin, plugin, vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: false, fx: 0, steps: new Array(64).fill(0), pitchN: 2 }),
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
    stepItemProbe: (prm, value, seed0, seed1) => {
      const a = newItem(), b = newItem();
      itemWrite(a, prm, 0, seed0); itemWrite(b, prm, 0, seed1);
      itemsSet([a, b], prm, value);
      return itemGet(b, prm);
    },
  };
}
