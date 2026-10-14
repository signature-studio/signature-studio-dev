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
const WRONG = (m) => new FlError(m || "Wrong number of function parameters or wrong parameter type", 5);
// mixer の色の R/B 入替え (REPORT_PY115.md §2)。MIX_DEFAULT_COLOR は未確定の既定値 (C の MIX_DEFAULT_COLOR と同じ仮置き)
const swapRb = (v) => ((v & 0xff) << 16) | (v & 0xff00) | ((v >>> 16) & 0xff);
const MIX_DEFAULT_COLOR = 0x5a6b7c;

export function createMockEngine() {
  const st = {
    tempo: 130,
    playing: false,
    changedFlag: 0, useMetronome: false, precount: false, recPPQ: 96,
    selStart: -1, selEnd: -1,
    selectedChannel: 0,
    channels: [
      { name: "Kick", plugin: "Sampler", vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: true, fx: 1, steps: new Array(64).fill(0) },
      { name: "Snare", plugin: "Sampler", vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: false, fx: 2, steps: new Array(64).fill(0) },
      { name: "3x Osc", plugin: "3x Osc", vol: 0.5, pan: 0.25, mute: false, solo: false, color: 0x7C5A6B, sel: false, fx: 0, steps: new Array(64).fill(0) },
    ],
    mixer: Array.from({ length: 127 }, (_, i) => ({
      name: i === 0 ? "Master" : i === 125 ? "Current" : `Insert ${i}`, vol: 0.8, pan: 0, mute: false, solo: false,
      color: 0, colorSet: false, sel: i === 0, slots: [], routes: i === 0 ? {} : { 0: 1.0 },
    })),
    playlist: Array.from({ length: 500 }, (_, i) => ({ name: `Track ${i + 1}`, color: 0x485156 })),
    windows: { 0: true, 1: false, 2: true, 3: false, 4: true, 5: false },
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
    "channels.getGridBit": (...a) => {
      arity(a, 2, 3);
      ix(a[0]); const p = ix(a[1]); argI(a, 2, 0);
      const k = ch(a[0]);
      if (p < 0 || p >= 64) throw RANGE();
      return !!k.steps[p];
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
    "ui.getVisible": (w) => !!st.windows[w],
    "ui.showWindow": (w) => { st.windows[w] = true; },
    "ui.hideWindow": (w) => { st.windows[w] = false; },
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
    // PY-96 (#2832): 選択範囲の読出し 4 件。PE 0xd786e0/0xd78700/0xd78500 は obj+0xd74 (start)・obj+0xd78 (end) を読み、
    // 0xd78720 は 0xe43e80 (start>=0 かつ end>=0) を bool で返す。未選択は負値。初期値 -1 は未実測の仮置き (provider/fl_engine.c と同じ)
    "arrangement.selectionStart": (...a) => { arity(a, 0, 0); return st.selStart; },
    "arrangement.selectionEnd": (...a) => { arity(a, 0, 0); return st.selEnd; },
    "arrangement.liveSelectionStart": (...a) => { arity(a, 0, 0); return st.selStart; },
    "arrangement.selectionIsActive": (...a) => { arity(a, 0, 0); return st.selStart >= 0 && st.selEnd >= 0; },
    "device.getPortNumber": () => st.devicePort ?? 0,
    "device.isAssigned": () => true,
    "device.setHasMeters": () => { st.hasMeters = true; },
    "device.forwardMIDICC": (message, mode = 1) => { st.midiOut.push({ api: "forwardMIDICC", message, mode }); },
    "device.midiOutMsg": (...a) => { st.midiOut.push({ api: "midiOutMsg", args: a }); },
    ...createIlmcp(st, {
      RANGE,
      INVALID: (m) => new FlError(m, 1),
      makeChannel: (plugin) => ({ name: plugin, plugin, vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: false, fx: 0, steps: new Array(64).fill(0) }),
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
  };
}
