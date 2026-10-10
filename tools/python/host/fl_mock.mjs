// FLEngine 模擬ホスト (PoC)。実装版では FLEngine wasm の export に置換される同一インタフェース:
//   engine.call("mixer.getTrackName", [index, ...]) -> any
// 返す number は整数なら int、実数なら float になる。整数値の float は F(x) で明示。
const F = (v) => ({ t: "D", v });

class FlError extends Error {
  constructor(msg, code) { super(msg); this.flCode = code; }
}
const RANGE = (m) => new FlError(m || "Index out of range", 4);

export function createMockEngine() {
  const st = {
    tempo: 130,
    playing: false,
    selectedChannel: 0,
    channels: [
      { name: "Kick", plugin: "Sampler", vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: true, fx: 1, steps: new Array(64).fill(0) },
      { name: "Snare", plugin: "Sampler", vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: false, fx: 2, steps: new Array(64).fill(0) },
      { name: "3x Osc", plugin: "3x Osc", vol: 0.5, pan: 0.25, mute: false, solo: false, color: 0x7C5A6B, sel: false, fx: 0, steps: new Array(64).fill(0) },
    ],
    mixer: Array.from({ length: 127 }, (_, i) => ({
      name: i === 0 ? "Master" : i === 125 ? "Current" : `Insert ${i}`, vol: 0.8, pan: 0, mute: false, solo: false,
      color: 0x5A6B7C, sel: i === 0, slots: [], routes: i === 0 ? {} : { 0: 1.0 },
    })),
    playlist: Array.from({ length: 500 }, (_, i) => ({ name: `Track ${i + 1}`, color: 0x485156 })),
    windows: { 0: true, 1: false, 2: true, 3: false, 4: true, 5: false },
    params: [{ name: "Cutoff", v: 0.5 }, { name: "Resonance", v: 0.2 }, { name: "Gain", v: 0.8 }],
    prScripts: {},
    log: [],
  };
  const ch = (i) => { if (!st.channels[i]) throw RANGE(); return st.channels[i]; };
  const tr = (i) => { if (!st.mixer[i]) throw RANGE(); return st.mixer[i]; };
  const tog = (cur, v) => (v === undefined || v === -1 ? !cur : !!v);

  const impl = {
    "channels.channelCount": () => st.channels.length,
    "channels.getChannelName": (i) => ch(i).name,
    "channels.setChannelName": (i, n) => { ch(i).name = n; },
    "channels.isChannelSelected": (i) => ch(i).sel,
    "channels.selectChannel": (i, v) => { ch(i).sel = tog(ch(i).sel, v); },
    "channels.deselectAll": () => { st.channels.forEach((c) => (c.sel = false)); },
    "channels.muteChannel": (i, v) => { ch(i).mute = tog(ch(i).mute, v); },
    "channels.soloChannel": (i) => { ch(i).solo = !ch(i).solo; },
    "channels.getChannelVolume": (i, mode) => F(mode ? 20 * Math.log10(Math.max(ch(i).vol, 1e-6) / 0.78125) : ch(i).vol),
    "channels.setChannelVolume": (i, v) => { ch(i).vol = v; },
    "channels.getChannelPan": (i) => F(ch(i).pan),
    "channels.setChannelPan": (i, v) => { ch(i).pan = v; },
    "channels.setChannelColor": (i, c) => { ch(i).color = c; },
    "channels.getTargetFxTrack": (i) => ch(i).fx,
    "channels.setTargetFxTrack": (i, t) => { ch(i).fx = t; },
    "channels.setGridBit": (i, pos, v) => { ch(i).steps[pos] = v ? 1 : 0; },
    "channels.quickQuantize": (i) => { ch(i); },
    "channels.showEditor": (i) => { ch(i); },
    "mixer.trackCount": () => st.mixer.length,
    "mixer.getTrackName": (i) => tr(i).name,
    "mixer.setTrackName": (i, n) => { tr(i).name = n; },
    "mixer.getTrackVolume": (i, mode) => F(mode ? 20 * Math.log10(Math.max(tr(i).vol, 1e-6) / 0.8) : tr(i).vol),
    "mixer.setTrackVolume": (i, v) => { tr(i).vol = v; },
    "mixer.getTrackPan": (i) => F(tr(i).pan),
    "mixer.setTrackPan": (i, v) => { tr(i).pan = v; },
    "mixer.setTrackColor": (i, c) => { tr(i).color = c; },
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
    "transport.isPlaying": () => st.playing,
    "playlist.trackCount": () => st.playlist.length,
    "playlist.getTrackName": (i) => st.playlist[i - 1]?.name ?? "",
    "playlist.setTrackName": (i, n) => { st.playlist[i - 1].name = n; },
    "playlist.setTrackColor": (i, c) => { st.playlist[i - 1].color = c; },
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
    "ilmcp.getBrowserNames": (name, rec) => ({ name, items: ["Fruity Slicer", "3x Osc", "Sampler"].map((n) => `${name || ""}/${n}`) }),
    "ilmcp.getHighlightNames": () => ["Toolbar: Show Piano roll", "Toolbar: Show playlist", "Toolbar: Show Mixer", "Toolbar: Show Channel Rack"],
    "ilmcp.showHighlight": (item, name, caption, cb) => { st.highlight = { item, name, caption, cb }; return true; },
    "ilmcp.addChannel": (plugin) => { st.channels.push({ name: plugin, plugin, vol: 0.78125, pan: 0, mute: false, solo: false, color: 0x5A6B7C, sel: false, fx: 0, steps: new Array(64).fill(0) }); return st.channels.length - 1; },
    "ilmcp.removeChannel": (i) => { st.channels.splice(i, 1); },
    "ilmcp.addEffect": (plugin, track, slot) => { tr(track).slots[slot] = plugin; return true; },
    "ilmcp.storePRScript": (name, src) => { st.prScripts[name] = src; return true; },
    "ilmcp.runPRScript": (src) => { st.log.push(["runPRScript", src.length]); return true; },
  };

  const record = [];
  return {
    state: st,
    record,
    call(name, args) {
      record.push([name, args]);
      const f = impl[name];
      if (!f) return null; // 未実装 API は None を返す (PoC)
      return f(...args);
    },
    implemented: () => Object.keys(impl),
  };
}
