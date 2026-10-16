// device 5 関数の差分検査: 同じ呼出し列を JS mock (host/fl_mock.mjs) と C provider (provider/fl_engine.c) に流し、
// 各呼出しの戻り値・エラー code と、forwardMIDICC / midiOutMsg の呼出し件数が一致することを確認する。
// PY-227 (#3655): midiOutMsg が送った 32bit word の列 (arg4 は channel ≥ 0 のとき bit 24–31) と、device 割当 (-7)・送出先 (-6) の経路も比べる。
// PY-231 (#3671): forwardMIDICC の -7・-6 の経路と、送った word (第 1 引数) も同じ列に入れて比べる。
//   node tests/device_diff.mjs     (前提: provider/build.sh 済み)
import fs from "node:fs";
import assert from "node:assert/strict";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const wasm = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const mock = createMockEngine();

const run = (eng, name, args) => {
  try {
    const v = eng.call(name, args);
    return { ok: v === undefined ? null : (v?.t === "D" ? v.v : v) };
  } catch (e) {
    return { code: e.flCode ?? null };
  }
};

const seq = [
  ["device.getPortNumber", []],
  ["device.isAssigned", []],
  ["device.setHasMeters", []],
  ["device.forwardMIDICC", [0x90 | (60 << 8) | (100 << 16) | (10 << 24), 2]],
  ["device.forwardMIDICC", [0xB0]],
  ["device.midiOutMsg", [0x90, 0, 60, 100]],
  ["device.midiOutMsg", [0xB0]],
  ["device.midiOutMsg", [0xB0, 2, 1, 127, 9]],
  ["device.midiOutMsg", [0x90, 1, 60, 100, 127]],
  ["device.midiOutMsg", [0xB0, -1, 1, 2, 9]],
  ["device.midiOutMsg", [0x1FF, 0x0F, 300, 40000, -1]],
  // PY-206 (#3494): PE で確定した 7 関数。getIdleElapsed・isMidiOutAssigned の値は仮置きで、mock と C が同じ値を返すことだけを見る
  ["device.createRefreshThread", []],
  ["device.destroyRefreshThread", []],
  ["device.fullRefresh", []],
  ["device.getIdleElapsed", []],
  ["device.isMidiOutAssigned", []],
  ["device.getMasterSync", []],
  ["device.setMasterSync", [true]],
  ["device.getMasterSync", []],
  ["device.setMasterSync", [false]],
  ["device.getMasterSync", []],
];

// mock は引数の個数・型を検査しない (既知の差)。C 側は署名どおりに拒否する (code 5) ことだけを wasm 単独で確認。
// midiOutMsg は FLEngine の書式 (i|iiii) で 5 個まで受理する (PY-102 / #2927)。6 個目から拒否する。
const rejects = [
  ["device.forwardMIDICC", []],
  ["device.forwardMIDICC", [1, "x"]],
  ["device.midiOutMsg", [0xB0, 2, 1, 127, 9, 9]],
  ["device.midiOutMsg", [0xB0, "x"]],
  ["device.getLinkedChannel", []],
  ["device.getLinkedChannel", [1, 2]],
  ["device.getLinkedChannel", ["x"]],
  ["device.createRefreshThread", [1]],
  ["device.getIdleElapsed", [1]],
  ["device.getMasterSync", [0]],
  ["device.isMidiOutAssigned", ["x"]],
  ["device.setMasterSync", []],
  ["device.setMasterSync", ["x"]],
];
const rejectDiffs = rejects.map(([name, args]) => ({ name, args, wasm: run(wasm, name, args) }))
  .filter((r) => r.wasm.code !== 5);

// PY-227: device 割当 [dev, link] を変えて -7 (device 無し)・-6 (送出先無し) を通す。PE 0xd747f0 は device を見てから送出先を見る (channel によらず先に判定)。
// PY-231: forwardMIDICC も midiOutMsg と同じ判定順と仮置き (REPORT_PY231 §1b)。
const linkSeq = [
  [[1, 1], ["device.midiOutMsg", [0x90, 1, 60, 100]]],
  [[0, 1], ["device.midiOutMsg", [0x90, 1, 60, 100]]],
  [[1, 0], ["device.midiOutMsg", [0x90, 1, 60, 100]]],
  [[1, 0], ["device.midiOutMsg", [0xB0]]],
  [[0, 0], ["device.midiOutMsg", [0xB0, 2, 1, 127, 9]]],
  [[1, 1], ["device.midiOutMsg", [0xB0, 2, 1, 127, 9]]],
  [[1, 1], ["device.forwardMIDICC", [0x90 | (60 << 8) | (100 << 16) | (10 << 24), 2]]],
  [[0, 1], ["device.forwardMIDICC", [0xB0, 2]]],
  [[1, 0], ["device.forwardMIDICC", [0xB0, 2]]],
];
const linkExpectCodes = ["ok", 7, 6, 6, 7, "ok", "ok", 7, 6];
const codeOf = (r) => ("code" in r ? r.code : "ok");

const diffs = [];
for (const [name, args] of seq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, mock: a, wasm: b });
}
const linkCodes = [];
for (const [[dev, link], [name, args]] of linkSeq) {
  mock.state.devAssigned = !!dev;
  mock.state.linkAssigned = !!link;
  wasm.setDeviceLink(dev, link);
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  linkCodes.push(codeOf(b));
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, dev, link, mock: a, wasm: b });
}

const mockOut = mock.state.midiOut.length;
const wasmOut = wasm.midiOutCount();
if (mockOut !== wasmOut) diffs.push({ state: "midiOut count", mock: mockOut, wasm: wasmOut });

assert.equal(wasm.call("device.getIdleElapsed", []).t, "D", "getIdleElapsed の戻りは float (D タグ)");
// 送った word 列 (midiOutMsg と forwardMIDICC の第 1 引数、呼出し順)。期待値は式の手計算 (両側が同じ誤りを持つ場合も落とす)
// PY-276: 末尾の forwardMIDICC(0x0A643C90, 2) は、同じ添字 2 で直前 (seq 先頭) に同じ値を送っているため送らない (値の変化が無い)
const expectWords = [0x0A643C90, 0xB0, 0x643C90, 0xB0, 0x097F01B2, 0x7F643C91, 0xB0, 0x9B412DFF, 0x643C91, 0x097F01B2];
const mockWords = mock.state.midiOut.map((m) => (m.api === "midiOutMsg" ? m.word : Number(m.message) >>> 0));
const wasmWords = wasm.midiWords();
if (JSON.stringify(mockWords) !== JSON.stringify(wasmWords)) diffs.push({ state: "midi word", mock: mockWords, wasm: wasmWords });
if (JSON.stringify(wasmWords) !== JSON.stringify(expectWords)) diffs.push({ state: "midi word expect", expect: expectWords, wasm: wasmWords });
if (JSON.stringify(linkCodes) !== JSON.stringify(linkExpectCodes)) diffs.push({ state: "link codes", expect: linkExpectCodes, wasm: linkCodes });

// PY-215 (#3568): getLinkedChannel (PE 0xd75d30)。-6/-7 の経路が無いので割当 [dev, link] の両方 (assigned・unassigned) で同じ戻り値。-1 → -1、連動表が空の index ≥ 0 → None (仮置き)
// PY-276 (#3949): forwardMIDICC は添字の値が変わったときだけ送る (PE 0xfdc8a0)。同じ値・同じ添字の連続は送らない (負例)。
// 添字ごとに独立。範囲外の添字は重複検出せず送る (仮置き)。mock と C の送出件数・word 列が一致することを見る。
const dedupSeq = [
  ["device.forwardMIDICC", [0x11, 3]],
  ["device.forwardMIDICC", [0x11, 3]],
  ["device.forwardMIDICC", [0x22, 3]],
  ["device.forwardMIDICC", [0x22, 3]],
  ["device.forwardMIDICC", [0x11, 3]],
  ["device.forwardMIDICC", [0x11, 4]],
  ["device.forwardMIDICC", [0x11, 4]],
  ["device.forwardMIDICC", [0x11, 99]],
  ["device.forwardMIDICC", [0x11, 99]],
];
const dedupExpectWords = [0x11, 0x22, 0x11, 0x11, 0x11, 0x11];
const dedupDiffs = [];
mock.state.devAssigned = true;
mock.state.linkAssigned = true;
wasm.setDeviceLink(1, 1);
mock.state.midiOut.length = 0;
const dedupBefore = wasm.midiOutCount();
for (const [name, args] of dedupSeq) {
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  if (JSON.stringify(a) !== JSON.stringify(b)) dedupDiffs.push({ name, args, mock: a, wasm: b });
}
const dedupWasmWords = wasm.midiWords().slice(-dedupExpectWords.length);
const dedupMockWords = mock.state.midiOut.map((m) => Number(m.message) >>> 0);
const dedupWasmCount = wasm.midiOutCount() - dedupBefore;
if (JSON.stringify(dedupMockWords) !== JSON.stringify(dedupExpectWords)) diffs.push({ state: "dedup mock words", expect: dedupExpectWords, mock: dedupMockWords });
if (JSON.stringify(dedupWasmWords) !== JSON.stringify(dedupExpectWords)) diffs.push({ state: "dedup wasm words", expect: dedupExpectWords, wasm: dedupWasmWords });
if (dedupWasmCount !== dedupExpectWords.length) diffs.push({ state: "dedup wasm count", expect: dedupExpectWords.length, wasm: dedupWasmCount });
if (dedupMockWords.length !== dedupExpectWords.length) diffs.push({ state: "dedup mock count", expect: dedupExpectWords.length, mock: dedupMockWords.length });
diffs.push(...dedupDiffs.map((d) => ({ dedup: true, ...d })));

// PY-276 追補 (review): 割当判定は重複判定より前 (midiOutNewMsg 0xd748e0 の -7 → -6 → 0xfdc8a0 を見た順。forwardMIDICC の判定順は仮置き・REPORT_PY231 §1b)。
// V を送った後に未割当で同じ添字・値を呼ぶと -7 (送らない)、割当に戻して同じ V を呼ぶと重複で送られない。
const assignDedupSeq = [
  [[1, 1], ["device.forwardMIDICC", [0x44, 5]], "ok"],
  [[0, 1], ["device.forwardMIDICC", [0x44, 5]], 7],
  [[1, 1], ["device.forwardMIDICC", [0x44, 5]], "ok"],
];
const assignDedupDiffs = [];
const assignDedupCodes = [];
const assignDedupBefore = wasm.midiOutCount();
mock.state.midiOut.length = 0;
for (const [[dev, link], [name, args], expect] of assignDedupSeq) {
  mock.state.devAssigned = !!dev;
  mock.state.linkAssigned = !!link;
  wasm.setDeviceLink(dev, link);
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  assignDedupCodes.push(codeOf(b));
  if (codeOf(b) !== expect) assignDedupDiffs.push({ state: "assign dedup expect", args, expect, wasm: b });
  if (JSON.stringify(a) !== JSON.stringify(b)) assignDedupDiffs.push({ name, args, dev, link, mock: a, wasm: b });
}
const assignDedupWords = wasm.midiWords().slice(-1);
const assignDedupMock = mock.state.midiOut.map((m) => Number(m.message) >>> 0);
if (wasm.midiOutCount() - assignDedupBefore !== 1) assignDedupDiffs.push({ state: "assign dedup wasm count", expect: 1, wasm: wasm.midiOutCount() - assignDedupBefore });
if (JSON.stringify(assignDedupMock) !== JSON.stringify([0x44]) || JSON.stringify(assignDedupWords) !== JSON.stringify([0x44])) assignDedupDiffs.push({ state: "assign dedup words", expect: [0x44], mock: assignDedupMock, wasm: assignDedupWords });
diffs.push(...assignDedupDiffs.map((d) => ({ assignDedup: true, ...d })));

const linkedIdx = [-1, 0, 7];
const linkedRes = [];
for (const [dev, link] of [[1, 1], [0, 0]]) {
  mock.state.devAssigned = !!dev;
  mock.state.linkAssigned = !!link;
  wasm.setDeviceLink(dev, link);
  for (const idx of linkedIdx) {
    const name = "device.getLinkedChannel", args = [idx];
    const a = run(mock, name, args);
    const b = run(wasm, name, args);
    linkedRes.push("code" in b ? `code ${b.code}` : b.ok);
    if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, dev, link, mock: a, wasm: b });
  }
}
const linkedExpect = [-1, null, null, -1, null, null];
if (JSON.stringify(linkedRes) !== JSON.stringify(linkedExpect)) diffs.push({ state: "linked channel expect", expect: linkedExpect, wasm: linkedRes });

// PY-4846 (#3568 子 B): getLinkedValue・getLinkedInfo・getLinkedParamName・getLinkedValueString。index -1 の経路だけ PE 確定 (REPORT_PY215 §1)。index >= 0 は未確定の未実装 error (mock と C で同じ code)
const linkedNames = ["device.getLinkedValue", "device.getLinkedInfo", "device.getLinkedParamName", "device.getLinkedValueString"];
const linkedNameRes = {};
for (const name of linkedNames) {
  for (const idx of [-1, 0]) {
    const a = run(mock, name, [idx]);
    const b = run(wasm, name, [idx]);
    linkedNameRes[`${name}(${idx})`] = "code" in b ? `code ${b.code}` : b.ok;
    if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args: [idx], mock: a, wasm: b });
  }
}
const linkedNameExpect = {
  "device.getLinkedValue(-1)": -1, "device.getLinkedValue(0)": "code 2",
  "device.getLinkedInfo(-1)": -1, "device.getLinkedInfo(0)": "code 2",
  "device.getLinkedParamName(-1)": "code 8", "device.getLinkedParamName(0)": "code 2",
  "device.getLinkedValueString(-1)": "code 8", "device.getLinkedValueString(0)": "code 2",
};
if (JSON.stringify(linkedNameRes) !== JSON.stringify(linkedNameExpect)) diffs.push({ state: "linked name expect", expect: linkedNameExpect, wasm: linkedNameRes });

// PY-260 (#3840) / PY-390 (#4830): findEventID (PE 0xd75b60) の未発見 -1、isDoubleClick (PE 0xd76060) の device 無し -7 と device 有りの未実装 (code 2)。mock と C で同じ code
const evtRes = {};
const evtCases = [
  [[1, 1], "device.findEventID", [5]], [[0, 0], "device.findEventID", [5, 1]], [[1, 1], "device.findEventID", []],
  [[1, 1], "device.isDoubleClick", [0]], [[0, 1], "device.isDoubleClick", [0]],
];
for (const [[dev, link], name, args] of evtCases) {
  mock.state.devAssigned = !!dev;
  mock.state.linkAssigned = !!link;
  wasm.setDeviceLink(dev, link);
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  evtRes[`${name}(${args.join(",")})/dev${dev}`] = "code" in b ? `code ${b.code}` : b.ok;
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args, dev, link, mock: a, wasm: b });
}
const evtExpect = {
  "device.findEventID(5)/dev1": -1, "device.findEventID(5,1)/dev0": -1, "device.findEventID()/dev1": "code 5",
  "device.isDoubleClick(0)/dev1": "code 2", "device.isDoubleClick(0)/dev0": "code 7",
};
if (JSON.stringify(evtRes) !== JSON.stringify(evtExpect)) diffs.push({ state: "event expect", expect: evtExpect, wasm: evtRes });
mock.state.devAssigned = true;
mock.state.linkAssigned = true;
wasm.setDeviceLink(1, 1);

// PY-5407 (#5947): repeatMidiEvent (PE 0xd762f0・"O|ii") と stopRepeatMidiEvent (PE 0xd764a0・引数なし)。device 無しは -7、device 有りは None (述語・vtbl 先の効果は仮置き)
// eventData は FlMidiMsg (Python 側オブジェクト) で、wasm の bridge は object を運べない (fl_provider.mjs は bytes/scalar/__cb のみ)。値は Uint8Array で代用し、status と arity の経路だけを比べる
const ev = new Uint8Array([0x90, 60, 100]);
const repeatRes = {};
const repeatCases = [
  [[1, 1], "device.repeatMidiEvent", [ev]], [[1, 1], "device.repeatMidiEvent", [ev, 10, 20]],
  [[0, 1], "device.repeatMidiEvent", [ev]], [[1, 1], "device.repeatMidiEvent", []],
  [[1, 1], "device.stopRepeatMidiEvent", []], [[0, 1], "device.stopRepeatMidiEvent", []],
];
for (const [[dev, link], name, args] of repeatCases) {
  mock.state.devAssigned = !!dev;
  mock.state.linkAssigned = !!link;
  wasm.setDeviceLink(dev, link);
  const a = run(mock, name, args);
  const b = run(wasm, name, args);
  repeatRes[`${name}(${args.length})/dev${dev}`] = "code" in b ? `code ${b.code}` : b.ok;
  if (JSON.stringify(a) !== JSON.stringify(b)) diffs.push({ name, args: args.length, dev, link, mock: a, wasm: b });
}
const repeatExpect = {
  "device.repeatMidiEvent(1)/dev1": null, "device.repeatMidiEvent(3)/dev1": null,
  "device.repeatMidiEvent(1)/dev0": "code 7", "device.repeatMidiEvent(0)/dev1": "code 5",
  "device.stopRepeatMidiEvent(0)/dev1": null, "device.stopRepeatMidiEvent(0)/dev0": "code 7",
};
if (JSON.stringify(repeatRes) !== JSON.stringify(repeatExpect)) diffs.push({ state: "repeat expect", expect: repeatExpect, wasm: repeatRes });
mock.state.devAssigned = true;
mock.state.linkAssigned = true;
wasm.setDeviceLink(1, 1);

assert.deepEqual(diffs, [], `device 差分 ${diffs.length} 件`);
assert.deepEqual(rejectDiffs, [], `署名違反が code 5 で拒否されない ${rejectDiffs.length} 件`);
console.log(JSON.stringify({
  calls: seq.length, link_calls: linkSeq.length, rejects: rejects.length, midi_out: wasmOut,
  midi_words: wasmWords.map((w) => w.toString(16).padStart(8, "0")), link_codes: linkCodes, linked_channel: linkedRes,
  diffs: 0, PASS: true,
}));
