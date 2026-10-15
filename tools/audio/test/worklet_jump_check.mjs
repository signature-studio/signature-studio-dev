// AU-29 (#3115): worklet の clock_jump 計上経路 (port の {ct, pn, cb} を含む) を node 上で駆動して検査する。
// 使い方: node tools/audio/test/worklet_jump_check.mjs [worklet のパス (既定 public/worklets/fl-audio-worklet.js)]
// 方法: fl-audio-worklet.js を vm で読み、currentFrame を飛ばして process() を呼ぶ (go=0 のまま、計上は go より前)。
//       performance を与える場合と与えない場合 (pn=-1 の経路) の両方を見る。失敗時は exit 1。
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(process.argv[2] ?? path.join(here, "../../../public/worklets/fl-audio-worklet.js"), "utf8");
const layoutTs = fs.readFileSync(path.join(here, "../../../src/runtime/audio-layout.ts"), "utf8");
const block = layoutTs.slice(layoutTs.indexOf("FLA_LAYOUT = {"), layoutTs.indexOf("} as const"));
const L = {};
for (const m of block.matchAll(/(\w+): (\d+)/g)) L[m[1]] = +m[2];

function run(withPerf) {
  const msgs = [];
  let registered = null;
  const ctx = { currentFrame: 0, currentTime: 0, sampleRate: 48000, console, Date, Atomics, Int32Array, Float32Array, Uint32Array, Float64Array, Math };
  if (withPerf) ctx.performance = { now: () => 1234.5 };
  ctx.AudioWorkletProcessor = class { constructor() { this.port = { postMessage: (m) => msgs.push(m) }; } };
  ctx.registerProcessor = (name, cls) => { if (name === "fl-audio-shim") registered = cls; };
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  const buffer = new SharedArrayBuffer(4096);
  const ctlPtr = 0;
  const i32 = new Int32Array(buffer, ctlPtr, 96);
  const node = new registered({ processorOptions: { layout: { ...L }, buffer, ctlPtr, capture: null } });
  i32[L.cb_count >> 2] = 7;   // producer の bufferSwitch 通し番号 (jump 時点で読まれる)
  const outputs = [[new Float32Array(128), new Float32Array(128)]];
  const frames = [0, 128, 384, 384, 512, 768];   // 384→384 = −128 の重複、384 (prev 128) = +128 の skip、512→768 = +128 の skip
  const cbAt = [7, 7, 9, 9, 9, 9];
  for (let k = 0; k < frames.length; k++) {
    ctx.currentFrame = frames[k];
    ctx.currentTime = frames[k] / 48000;
    i32[L.cb_count >> 2] = cbAt[k];
    node.process([], outputs);
  }
  return msgs.filter((m) => m.type === "clock_jump");
}

let ok = true;
const check = (name, cond, detail) => { if (!cond) ok = false; console.log(`${cond ? "PASS" : "FAIL"} ${name} ${detail ?? ""}`); };

const withPerf = run(true);
check("jump 件数 (performance あり)", withPerf.length === 3, `n=${withPerf.length} (期待 3: skip, dup, skip)`);
const first = withPerf[0] ?? {};
check("1 件目 d/frame/cb/ct/pn", first.d === 128 && first.frame === 384 && first.cb === 9 && first.ct === 384 / 48000 && first.pn === 1234.5,
  `d=${first.d} frame=${first.frame} cb=${first.cb} ct=${first.ct} pn=${first.pn}`);
const dup = withPerf[1] ?? {};
check("2 件目 重複 (d<0) の cb 通し番号", dup.d === -128 && dup.cb === 9, `d=${dup.d} cb=${dup.cb}`);

const noPerf = run(false);
const np = noPerf[0] ?? {};
check("performance 無し: pn = -1 (例外なし)", noPerf.length === 3 && np.pn === -1 && np.ct === 384 / 48000, `n=${noPerf.length} pn=${np.pn} ct=${np.ct}`);

console.log(ok ? "OK: worklet jump 計上経路は PASS" : "NG: 失敗あり");
process.exit(ok ? 0 : 1);
