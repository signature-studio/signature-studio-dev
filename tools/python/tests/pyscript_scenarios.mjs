// .pyscript ローダ + flpianoroll の回帰シナリオ (PY-5 / #79, ブラウザ実行検証 PY-11 / #466)。
// 実行環境 (node / Chrome) に依存しない本体。呼び出し側が FlPython・createMockEngine・スクリプト本文・ids・inventory・flpyUrl を渡す。
// 返り値: results = [{name, ok, detail}]、outputs = run_pyscript の {name, values, score(入力), result} 全件 (環境間の出力一致比較用)。
// 判定は各スクリプトごとに「JS 側の独立 oracle (手導出 or 別算法)」と照合する。ネガティブコントロールを末尾に置く。
export async function runScenarios({ FlPython, createMockEngine, PR, REMOTE, AUDIO, ids, inv, flpyUrl }) {
const enc = (s) => new TextEncoder().encode(s);
const results = [];
const outputs = [];
const check = (name, ok, detail = "") => { results.push({ name, ok: !!ok, detail }); if (!ok) console.log("FAIL", name, detail); };
const info = (name, detail) => console.log("INFO", name, detail);
// ---- wasm Python 起動 ----
async function boot(extraFiles = {}) {
  const engine = createMockEngine();
  const files = {};
  const all = { ...Object.fromEntries(Object.entries(PR).map(([k, v]) => [k, v[1]])), ...extraFiles };
  for (const [k, s] of Object.entries(all)) files[`/fl/Scripts/${k}.pyscript`] = enc(s);
  for (const [k, v] of Object.entries(REMOTE)) files[`/fl/Scripts/${k}.pyscript`] = enc(v[1]);
  for (const [f, s] of AUDIO) files[`/fl/Scripts/audio_${f}.pyscript`] = enc(s);
  const py = await FlPython.create({ flpyUrl, engine, ids, files, onStdout: () => {}, onStderr: () => {} });
  await py.run("import fl_rt, flpianoroll, enveditor; flpianoroll.install(); enveditor.install(); fl_rt.install_flapi()");
  return { py, engine };
}
const load = async (py, name) => py.call("fl_rt:load_pyscript", { path: `/fl/Scripts/${name}.pyscript`, name });
const run = async (py, name, score, values = {}) => {
  const r = await py.call("fl_rt:run_pyscript", { name, score, values });
  if (r.err) throw new Error(`${name}: ${r.err}`);
  outputs.push({ name, values, score, result: r.ok });
  return r.ok;
};

// ---- 部品 ----
let seed = 12345;
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
const N = (o = {}) => ({ number: 60, time: 0, length: 24, group: 0, color: 0, pitchofs: 0, repeats: 0, pan: 0.5, velocity: 0.8,
  release: 0, fcut: 0.5, fres: 0.5, slide: false, porta: false, muted: false, selected: false, ...o });
const near = (a, b) => Math.abs(a - b) < 1e-9;
const key = (n) => `${n.time}|${n.number}|${n.length}|${n.color}`;
const sameSet = (a, b) => { const x = a.map(key).sort(), y = b.map(key).sort(); return x.length === y.length && x.every((v, i) => v === y[i]); };

const { py, engine } = await boot();
for (const n of Object.keys(PR)) {
  const r = await load(py, n);
  check(`load ${n}`, r.ok && r.ok.createDialog && r.ok.apply, JSON.stringify(r));
}

// ===== 1. Euclidean: 整数算術の oracle (onset(i) = i==0 || floor(i*o/p) != floor((i-1)*o/p)、offset は循環シフト) =====
{
  const oracle = (p, o, off, num) => {
    const base = Array.from({ length: p }, (_, i) => o > 0 && (i === 0 || Math.floor((i * o) / p) !== Math.floor(((i - 1) * o) / p)));
    return base.flatMap((_, j) => (o > 0 && base[(((j - off) % p) + p) % p] ? [N({ time: j * 24, number: num, length: 24, color: 0 })] : []));
  };
  const def = await run(py, "Euclidean", { PPQ: 96, notes: [] });
  const expDef = [...oracle(32, 8, 0, 36), ...oracle(32, 13, 0, 37), ...oracle(32, 18, 0, 42)];
  check("Euclidean default (CH1 8/CH2 13/CH3 18, 32 steps)", sameSet(def.score.notes, expDef) && def.warnings.length === 0, `${def.score.notes.length} vs ${expDef.length}`);
  const v = { "CH1: Onsets": 9, "CH1: Offset": 3, "CH2: Onsets": 15, "CH2: Offset": 5, "CH3: Onsets": 21, "CH3: Offset": 7,
    "CH1: Note #": 36, "CH2: Note #": 38, "CH3: Note #": 42, "Pattern Length": 24 };
  const c = await run(py, "Euclidean", { PPQ: 96, notes: [] }, v);
  const exp = [...oracle(24, 9, 3, 36), ...oracle(24, 15, 5, 38), ...oracle(24, 21, 7, 42)];
  check("Euclidean custom (24 steps, offsets 3/5/7)", sameSet(c.score.notes, exp) && c.warnings.length === 0, `${c.score.notes.length} vs ${exp.length}`);
  check("Euclidean dialog 10 controls", c.dialog.controls.length === 10 && c.dialog.title === "Euclidean");
}

// ===== 2. Selector: JS 再実装の oracle (3 構成 × 40 ノート) =====
{
  const notes = Array.from({ length: 40 }, () => N({ number: Math.floor(rnd() * 132), length: 1 + Math.floor(rnd() * 200),
    velocity: Math.round(rnd() * 100) / 100, pan: Math.round(rnd() * 100) / 100, fcut: Math.round(rnd() * 100) / 100,
    fres: Math.round(rnd() * 100) / 100, pitchofs: Math.floor(rnd() * 241) - 120, slide: rnd() < 0.5, porta: rnd() < 0.5,
    muted: rnd() < 0.3, color: Math.floor(rnd() * 16) }));
  const D = { "Note nr (min)": 0, "Note nr (max)": 131, "Duration (min)": 0, "Duration (max)": 100, "Velocity (min)": 0, "Velocity (max)": 100,
    "Pan (min)": -100, "Pan (max)": 100, "Filter cutoff (min)": 0, "Filter cutoff (max)": 100, "Resonance (min)": 0, "Resonance (max)": 100,
    "Pitch offset (min)": -120, "Pitch offset (max)": 120, "Note pitch": 12, Slide: 2, Portamento: 2, "Muted notes": 2, "Color / Midi ch": 16, "Invert selection": 0 };
  const oracle = (n, v) => {
    let m = n.number >= v["Note nr (min)"] && n.number <= v["Note nr (max)"] && n.length >= v["Duration (min)"] && n.length <= v["Duration (max)"] &&
      n.velocity >= v["Velocity (min)"] / 100 && n.velocity <= v["Velocity (max)"] / 100 &&
      n.pan >= (v["Pan (min)"] + 100) / 200 && n.pan <= (v["Pan (max)"] + 100) / 200 &&
      n.fcut >= v["Filter cutoff (min)"] / 100 && n.fcut <= v["Filter cutoff (max)"] / 100 &&
      n.fres >= v["Resonance (min)"] / 100 && n.fres <= v["Resonance (max)"] / 100 &&
      n.pitchofs >= v["Pitch offset (min)"] && n.pitchofs <= v["Pitch offset (max)"];
    if (v["Note pitch"] !== 12 && v["Note pitch"] !== n.number % 12) m = false;
    for (const [c, a] of [["Slide", n.slide], ["Portamento", n.porta], ["Muted notes", n.muted]]) if (v[c] !== 2 && !v[c] !== a) m = false;
    if (v["Color / Midi ch"] !== 16 && v["Color / Midi ch"] !== n.color) m = false;
    return m !== (v["Invert selection"] !== 0);
  };
  const cfgs = { defaults: {}, narrow: { "Note nr (min)": 40, "Note nr (max)": 90, "Velocity (min)": 20, "Velocity (max)": 80, "Pan (min)": -50, "Pan (max)": 60,
      "Muted notes": 1, Slide: 0, "Duration (max)": 150 },
    inverted: { "Note pitch": 4, "Invert selection": 1, "Duration (max)": 1000 } };
  for (const [nm, vals] of Object.entries(cfgs)) {
    const r = await run(py, "Selector", { PPQ: 96, notes }, vals);
    const full = { ...D, ...vals };
    const bad = r.score.notes.filter((n, i) => n.selected !== oracle(notes[i], full)).length;
    const nsel = r.score.notes.filter((n) => n.selected).length;
    check(`Selector ${nm}: 40 ノートの selected が oracle と一致 (選択 ${nsel})`, bad === 0 && r.warnings.length === 0, `mismatch=${bad}`);
    if (nm !== "defaults") check(`Selector ${nm}: 非自明 (0<選択<40)`, nsel > 0 && nsel < 40, String(nsel));
  }
}

// ===== 3. Repeater: 件数・時刻・長さ・色・velocity の閉形式 oracle =====
{
  const src = Array.from({ length: 6 }, (_, i) => N({ number: 48 + i, time: i * 100, length: 60 + i * 10, color: i % 4, velocity: 0.5 + i * 0.05, selected: true }));
  const r = await run(py, "Repeater", { PPQ: 96, notes: src });
  const exp = [];
  for (const n of src) {
    exp.push({ ...n, length: Math.min(n.length, 24) - 1 });
    for (let x = 0; x < 3; x++) exp.push({ ...n, time: n.time + (x + 1) * 24, length: 24, color: (n.color + 2 + x) & 15 });
  }
  check("Repeater default: 6 → 24 ノート", r.score.notes.length === 24, String(r.score.notes.length));
  check("Repeater default: time/number/length/color 集合一致", sameSet(r.score.notes, exp));
  const byKey = (xs) => [...xs].sort((a, b) => key(a).localeCompare(key(b)));
  const gotS = byKey(r.score.notes), expS = byKey(exp);
  check("Repeater default: velocity 一致", gotS.every((n, i) => near(n.velocity, expS[i].velocity)));
  const r2 = await run(py, "Repeater", { PPQ: 96, notes: src }, { Repeats: 2, "Spacing dec/inc": 1.2, "Velocity dec/inc": 0.9, "Colorize notes": 0 });
  const e2 = [];
  for (const n of src) {
    e2.push({ ...n, length: 23 });
    for (let x = 0; x < 2; x++) e2.push({ ...n, time: Math.trunc(n.time + 1.2 ** (x + 1) * (x + 1) * 24), length: 24, velocity: n.velocity * 0.9 ** (x + 1) });
  }
  check("Repeater Repeats=2/spacing 1.2/vel 0.9: 18 ノート + 集合一致", r2.score.notes.length === 18 && sameSet(r2.score.notes, e2), String(r2.score.notes.length));
  const vs = r2.score.notes.filter((n) => n.length === 24).map((n) => n.velocity).sort((a, b) => a - b);
  const ve = e2.filter((n) => n.length === 24).map((n) => n.velocity).sort((a, b) => a - b);
  check("Repeater: velocity 減衰一致", vs.every((v, i) => near(v, ve[i])));
}

// ===== 4. Humanize: 恒等・決定論・境界 =====
{
  const src = Array.from({ length: 12 }, (_, i) => N({ number: 50 + i, time: 200 + i * 48, length: 40 + i, velocity: 0.3 + i * 0.04, selected: true }));
  const idv = { "Start Time Range": 0, "Duration Range": 0, "Velocity Range": 0, Seed: 2 };
  const id = await run(py, "Humanize", { PPQ: 96, notes: src }, idv);
  check("Humanize range=0/offset=0 は恒等", id.score.notes.every((n, i) => n.time === src[i].time && n.length === src[i].length && near(n.velocity, src[i].velocity)));
  const off = await run(py, "Humanize", { PPQ: 96, notes: src }, { ...idv, "Start Time Offset": 0.5, "Duration Offset": 0.5, "Velocity Offset": 0.25, "Start Time Ref": 1 });
  check("Humanize offset (ref 1/64 → 6 ticks): time+3 / length*1.5 / velocity*1.25(≤1)",
    off.score.notes.every((n, i) => n.time === src[i].time + 3 && n.length === Math.trunc(src[i].length * 1.5) && near(n.velocity, Math.min(src[i].velocity * 1.25, 1))));
  info("Humanize offset 正常系 time 値列 (src+3 が期待値)", JSON.stringify(off.score.notes.map((n) => n.time)));
  const rv = { "Start Time Range": 0.5, "Duration Range": 0.3, "Velocity Range": 0.4, Seed: 2, "Start Time Ref": 0 };
  const a = await run(py, "Humanize", { PPQ: 96, notes: src }, rv);
  const b = await run(py, "Humanize", { PPQ: 96, notes: src }, rv);
  const c = await run(py, "Humanize", { PPQ: 96, notes: src }, { ...rv, Seed: 5 });
  check("Humanize 同 seed は決定論", JSON.stringify(a.score.notes) === JSON.stringify(b.score.notes));
  check("Humanize 別 seed は結果が変わる", JSON.stringify(a.score.notes) !== JSON.stringify(c.score.notes));
  const maxTicks = 96 * 2 ** -3; // ref 0 = 1/32
  check("Humanize 時刻ジッタが ±range*max_ticks (+int 切捨 1) 内",
    a.score.notes.every((n, i) => Math.abs(n.time - src[i].time) <= 0.5 * maxTicks + 1) && a.score.notes.some((n, i) => n.time !== src[i].time));
  check("Humanize velocity ≤ 1・length 範囲内",
    a.score.notes.every((n, i) => n.velocity <= 1 && n.length >= Math.trunc(src[i].length * 0.7) - 1 && n.length <= Math.trunc(src[i].length * 1.3) + 1));
}

// ===== 5. Arpeggiator: 手導出 (3 和音 → 4 ステップ) =====
{
  const chord = [60, 64, 67].map((x) => N({ number: x, time: 0, length: 96, selected: true }));
  const seq = (mode, prob = 1) => run(py, "Arpeggiator", { PPQ: 96, notes: chord }, { Mode: mode, "Note Prob": prob });
  const up = await seq(1), dn = await seq(2);
  const ex = (nums) => nums.map((x, i) => N({ number: x, time: i * 24, length: 24 }));
  check("Arpeggiator Increasing = 60,64,67,60 @0/24/48/72 (length 24)", sameSet(up.score.notes, ex([60, 64, 67, 60])), JSON.stringify(up.score.notes.map(key)));
  check("Arpeggiator Decreasing = 60,67,64,60", sameSet(dn.score.notes, ex([60, 67, 64, 60])), JSON.stringify(dn.score.notes.map(key)));
  const none = await seq(0, 0);
  check("Arpeggiator Note Prob=0 → 全ノート消去 (選択ノートのみ clear)", none.score.notes.length === 0);
  const r1 = await run(py, "Arpeggiator", { PPQ: 96, notes: chord }, { Mode: 0, Seed: 4 });
  const r2 = await run(py, "Arpeggiator", { PPQ: 96, notes: chord }, { Mode: 0, Seed: 4 });
  check("Arpeggiator Random 同 seed は決定論・音は和音内・時刻は 24 の倍数",
    JSON.stringify(r1.score.notes) === JSON.stringify(r2.score.notes) && r1.score.notes.length > 0 &&
      r1.score.notes.every((n) => [60, 64, 67].includes(n.number) && n.time % 24 === 0 && n.time <= 72));
}

// ===== 6. 同梱 Remote Scripts 5 本 (flapi のみ) =====
{
  for (const k of Object.keys(REMOTE)) { const r = await load(py, k); check(`load Remote ${k}`, !!r.ok, JSON.stringify(r)); }
  const calls = (since) => engine.record.slice(since).map(([n, a]) => `${n}(${a.join(",")})`);
  let m = engine.record.length;
  const r1 = await py.call("filleach:filleach", [4, 0, 100]);
  check("filleach(4,0,100) → selectedChannel(0,0,1) + fillEachNSteps(0,4,0,100,1)",
    !r1.err && JSON.stringify(calls(m)) === JSON.stringify(["channels.selectedChannel(0,0,1)", "channels.fillEachNSteps(0,4,0,100,1)"]), JSON.stringify(calls(m)));
  check("filleach 後のモック状態 (steps 0,4,8,... = 16 個)", engine.state.channels[0].steps.reduce((a, b) => a + b, 0) === 16);
  m = engine.record.length;
  await py.call("rerollLSloop:rerollLSloop", []);
  await py.call("rerollLSloop:rerollLSloop", [-2]);
  await py.call("rerollLSsample:rerollLSsample", []);
  await py.call("rerollLSsteps:rerollLSsteps", []);
  check("reroll 4 呼出しの flapi 列", JSON.stringify(calls(m)) === JSON.stringify([
    // 手導出: loop() は既定 -1 (= 全チャンネル、selectedChannel を引かない) / loop(-2) は val<-1 なので選択チャンネル (mock: 0) /
    // sample() も既定 -1 (コメントの "selected channel" とは異なり、コードは val<-1 の時だけ選択チャンネルを引く) / steps() は常に選択チャンネル
    "channels.rerollLoopStarterLoop(-1,1)", "channels.selectedChannel(0,0,1)", "channels.rerollLoopStarterLoop(0,1)",
    "channels.rerollLoopStarterSample(-1,1)", "channels.selectedChannel(0,0,1)", "channels.rerollLoopStarterSteps(0,1)"]), JSON.stringify(calls(m)));
  const q = async (f, a) => (await py.call(`flrInit:${f}`, a)).ok;
  check("flrInit helpers (mapToRange/mapToIntRange/mapToValues/noteToNum/flrInit)",
    near(await q("mapToRange", [0.5, 10, 20]), 15) && (await q("mapToRange", [2, 10, 20])) === 20 && (await q("mapToIntRange", [0.5, 0, 5])) === 2 &&
    (await q("mapToValues", [1, ["a", "b", "c"]])) === "c" && (await q("mapToValues", [0.5, []])) === -1 && (await q("noteToNum", ["db"])) === 1 && (await q("noteToNum", ["zz"])) === 0 && (await q("flrInit", [])) === null);
}

// ===== 7. 同梱 Audio scripts 12 本の調査 (enveditor 依存。flapi のみで動くものの有無) =====
{
  const imports = (s) => [...s.matchAll(/^\s*(?:from\s+(\w+)\s+import|import\s+(\w+))/gm)].map((x) => x[1] || x[2]);
    const invAudio = Object.entries(inv.groups).filter(([g]) => g.includes("Audio scripts")).flatMap(([, v]) => v);
  check("Audio scripts 12 本 (inventory と件数一致)", AUDIO.length === 12 && invAudio.length === 12, `${AUDIO.length}/${invAudio.length}`);
  check("Audio 12 本の FL module 依存は enveditor のみ (inventory と別算法で一致)",
    AUDIO.every(([, s]) => imports(s).every((x) => x === "enveditor" || x === "math")) && invAudio.every((f) => JSON.stringify(f.imports_fl) === '["enveditor"]'));
  // PY-23 (#1054): enveditor 実装後の実行検証。各本を Title / 先頭のシグネチャで特定 (ブロック名は持たない)
  const by = (re) => { const h = AUDIO.filter(([, s]) => re.test(s)); if (h.length !== 1) throw new Error(`audio ${re}: ${h.length}`); return h[0][0]; };
  const A = {
    amp: by(/ScriptDialog\('Amp'/), br: by(/ScriptDialog\('Bit reduction'/), dest: by(/ScriptDialog\('Destructoid'/),
    lim: by(/ScriptDialog\('Limiter'/), old: by(/ScriptDialog\('Old school'/), rm: by(/ScriptDialog\('Ring modulation'/),
    pulse: by(/ScriptDialog\('Pulse generator'/), saw: by(/ScriptDialog\('Saw generator'/), sil: by(/ScriptDialog\('Silence generator'/),
    sine: by(/ScriptDialog\('Sine generator'/), region: by(/^for i in range\(EditorSample\.RegionCount\)/m), ptE: by(/ScriptDialog\('Play To End'/),
  };
  const ld = (f, sample, sel) => py.call("fl_rt:load_audio", { path: `/fl/Scripts/audio_${f}.pyscript`, name: `audio_${f}`, sample, selection: sel });
  const ra = (f, sample, sel, values) => py.call("fl_rt:run_audio", { name: `audio_${f}`, sample, selection: sel, values });
  const mono = (n, fn = (i) => 0) => ({ ch: [Array.from({ length: n }, (_, i) => fn(i))], rate: 44100 });
  const loaded = [];
  for (const [f] of AUDIO) { const r = await ld(f, mono(4), [0, 0]); loaded.push(r.ok ? "ok" : r.err); }
  check("Audio 12 本: enveditor を import して load が通る", loaded.filter((x) => x === "ok").length === 12, loaded.filter((x) => x !== "ok").join(" | "));
  const ex = [];
  const exOk = async (name, fn) => { try { const r = await fn(); if (r.err) throw new Error(r.err); ex.push(name); return r.ok; } catch (e) { return { err: String(e) }; } };
  // Amp: 選択範囲 [2,5] だけ Volume 倍
  {
    const x = [1, -1, 0.5, 0.25, 0.75, -0.5, 0.1, 0.2];
    const r = await exOk("amp", () => ra(A.amp, mono(8, (i) => x[i]), [2, 5], { Volume: 0.5 }));
    const exp = x.map((v, i) => (i >= 2 && i <= 5 ? v * 0.5 : v));
    const got = r.sample ? r.sample.ch[0] : [];
    check("Audio Amp: 選択 [2,5] のみ Volume 0.5 倍 (独立 oracle)", got.length === 8 && got.every((v, i) => near(v, exp[i])), JSON.stringify(got));
  }
  // Old school: SampleRate 11000、全体を 8bit 量子化 (round(s*128)/128。0.5 境界を避けた入力)
  {
    const x = [0.3, -0.7, 0.1234, 0.9, -0.333, 0.6];
    const r = await exOk("old", () => ra(A.old, mono(6, (i) => x[i]), [0, 0], {}));
    const exp = x.map((v) => Math.round(v * 128) / 128);
    check("Audio Old school: SampleRate=11000 かつ 8bit 量子化 (独立 oracle)", r.sample && r.sample.rate === 11000 && r.sample.ch[0].every((v, i) => near(v, exp[i])), JSON.stringify(r.sample && r.sample.ch[0]));
  }
  // Silence generator: Length 0 → 指定長の無音 (選択範囲 [0,99])
  {
    const r = await exOk("sil", () => ra(A.sil, { ch: [[]], rate: 44100 }, [0, 99], { "Length (samples)": 100 }));
    check("Audio Silence generator: Length 100 の無音 (独立 oracle)", r.sample && r.sample.ch[0].length === 100 && r.sample.ch[0].every((v) => v === 0));
  }
  // Sine generator: Length 0 → 1000ms=44100 samples、選択 [0,999] に 1000Hz 正弦 (位相 0 基準は ASSUMPTION)
  {
    const r = await exOk("sine", () => ra(A.sine, { ch: [[]], rate: 44100 }, [0, 999], { "Freq (Hz)": 1000, Phase: 0, Volume: 1 }));
    const g = r.sample ? r.sample.ch[0] : [];
    const exp = Array.from({ length: 1000 }, (_, n) => Math.sin((2 * Math.PI * 1000 * n) / 44100));
    check("Audio Sine generator: 44100 samples・選択内が 1000Hz 正弦 (独立 oracle)", g.length === 44100 && exp.every((v, n) => near(g[n], v)) && g.slice(1000).every((v) => v === 0), `len=${g.length}`);
  }
  // Region: 各 region の SampleEnd = 次 region の SampleStart、最後は Length-1 (トップレベルで実行)
  {
    const r = await py.call("fl_rt:load_audio", { path: `/fl/Scripts/audio_${A.region}.pyscript`, name: `audio_${A.region}`, sample: { ch: [Array.from({ length: 100 }, () => 0)], rate: 44100, regions: [{ name: "a", start: 10, end: 20 }, { name: "b", start: 40, end: 60 }, { name: "c", start: 70, end: 90 }] }, selection: [0, 0] });
    const ends = r.ok ? r.ok.sample.regions.map((x) => x.end) : [];
    check("Audio Region 変換: SampleEnd = 次 Start / 末尾は Length-1 (独立 oracle)", JSON.stringify(ends) === "[40,70,99]", JSON.stringify(ends));
    if (!r.err) ex.push("region");
  }
  // Play To End: Reset/Selection 既定 (No) → 全 region の SampleEnd = Length-1
  {
    const r = await py.call("fl_rt:load_audio", { path: `/fl/Scripts/audio_${A.ptE}.pyscript`, name: `audio_${A.ptE}`, sample: { ch: [Array.from({ length: 100 }, () => 0)], rate: 44100, regions: [{ name: "a", start: 10, end: 20 }, { name: "b", start: 40, end: 60 }] }, selection: [0, 0] });
    const ends = r.ok ? r.ok.sample.regions.map((x) => x.end) : [];
    check("Audio Play To End: 既定 (No/No) で全 region の SampleEnd = Length-1 (独立 oracle)", JSON.stringify(ends) === "[99,99]", JSON.stringify(ends));
    if (!r.err) ex.push("playtoend");
  }
  // 残りは実行が例外なく完了することを確認 (数値 oracle は未実装。ring mod は clipboard mock が空のため変化なしが期待)
  for (const k of ["br", "dest", "lim", "rm", "pulse", "saw"]) {
    const r = await exOk(k, () => ra(A[k], mono(64, (i) => Math.sin(i / 5) * 0.5), [0, 63], {}));
    check(`Audio ${k}: 実行が例外なく完了`, !r.err, r.err || "");
  }
  info("Audio 実行 OK 本数", `${ex.length}`);
  // NEG-d: Amp の適用量を 1 箇所改変 (value → value*2) → 独立 oracle と不一致になる (FAIL を検出)
  const ampSrc = AUDIO.find(([f]) => f === A.amp)[1];
  const ampMut = ampSrc.replace("EditorSample.AmpFromTo(x1,x2,value)", "EditorSample.AmpFromTo(x1,x2,value*2)");
  const { py: p3 } = await boot({ AmpMut: ampMut });
  await p3.call("fl_rt:load_pyscript", { path: "/fl/Scripts/AmpMut.pyscript", name: "AmpMut" });
  const mr = await p3.call("fl_rt:run_audio", { name: "AmpMut", sample: mono(8, (i) => [1, -1, 0.5, 0.25, 0.75, -0.5, 0.1, 0.2][i]), selection: [2, 5], values: { Volume: 0.5 } });
  const mg = mr.ok ? mr.ok.sample.ch[0] : [];
  check("NEG-d: Amp の適用量を改変 → oracle 不一致 (FAIL を検出)", mr.ok && !near(mg[2], 0.5 * 0.5), `mg[2]=${mg[2]} (正常 0.25)`);
  await p3.terminate();
}

await py.terminate();

// ===== ネガティブコントロール =====
{
  // (a) Euclidean のアルゴリズムを 1 箇所壊す → oracle 不一致を検出できること
  const mut = PR.Euclidean[1].replace("current := int(i * slope)", "current := int(i * slope + 0.5)");
  const { py: p2 } = await boot({ EuclideanMut: mut });
  await load(p2, "EuclideanMut");
  const a = await run(p2, "EuclideanMut", { PPQ: 96, notes: [] });
  const good = await run(p2, "Euclidean", { PPQ: 96, notes: [] }).catch(() => null);
  const oracle = (p, o, num) => Array.from({ length: p }, (_, i) => (i === 0 || Math.floor((i * o) / p) !== Math.floor(((i - 1) * o) / p) ? N({ time: i * 24, number: num }) : null)).filter(Boolean);
  const exp = [...oracle(32, 8, 36), ...oracle(32, 13, 37), ...oracle(32, 18, 42)];
  check("NEG-a: Euclidean を 1 箇所改変 → oracle 不一致 (FAIL を検出)", !sameSet(a.score.notes, exp), `改変版 ${a.score.notes.length} ノート vs oracle ${exp.length}`);
  info("NEG-a 改変版ノート数 / oracle ノート数", `${a.score.notes.length} / ${exp.length}`);
  // (b) Score.getNote が live 参照でなくコピーを返す → Humanize の in-place 更新が失われ offset テストが FAIL するはず
  await p2.run("import flpianoroll; flpianoroll.Score.getNote = lambda s, i: s._notes[i].clone()");
  await load(p2, "Humanize");
  const src = Array.from({ length: 4 }, (_, i) => N({ number: 50 + i, time: 200 + i * 48, length: 40, selected: true }));
  const h = await run(p2, "Humanize", { PPQ: 96, notes: src }, { "Start Time Range": 0, "Duration Range": 0, "Velocity Range": 0, "Start Time Offset": 0.5, "Start Time Ref": 1, Seed: 2 });
  check("NEG-b: getNote が clone を返す → Humanize offset が反映されない (FAIL を検出)", h.score.notes.every((n, i) => n.time === src[i].time), JSON.stringify(h.score.notes.map((n) => n.time)));
  info("NEG-b 改変版 time 値列 (元 time 200,248,296,344 のまま)", JSON.stringify(h.score.notes.map((n) => n.time)));
  // (c) typo したフォーム値は黙って無視されず KeyError
  await load(p2, "Euclidean");
  const bad = await p2.call("fl_rt:run_pyscript", { name: "Euclidean", score: { PPQ: 96, notes: [] }, values: { "CH9: Onsets": 3 } });
  check("NEG-c: 存在しないコントロール名は KeyError", bad.err && /KeyError/.test(bad.err), bad.err || "");
  await p2.terminate();
}

return { results, outputs };
}
