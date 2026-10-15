// PY-8 (#80) 診断: flapi 1 回 (Python 込み) の往復時間と、呼出し間隔 (gap) の関係。
//   node tests/rtt_gap_bench.mjs [n=300] [trials=3] [gapsMs=0,2,20] [mode=sleep|spin]   (前提: build_flpy.sh 済み)
// rtt_bench.mjs と同じ FlPython + mock engine。各呼出しの前に host が gap ms だけ待つ。
// mode=sleep は setTimeout で待つ (host の event loop が idle)、mode=spin は回し続ける (host は起きたまま)。
// 1 回の py.run = `channels.channelCount()` 1 回 (flapi 1 回)。gap=0 は連続呼出しの対照。
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const py = await FlPython.create({ flpyUrl: new URL("dist/flpy.js", root), engine: createMockEngine(), ids, files: {}, onStdout() {}, onStderr() {} });
await py.run("import fl_rt\nfl_rt.install_flapi()");
await py.run("import channels\nchannels.channelCount()");
const n = Number(process.argv[2] || 300);
const trials = Number(process.argv[3] || 3);
const gaps = (process.argv[4] || "0,2,20").split(",").map(Number);
const mode = process.argv[5] || "sleep";
const pct = (a, p) => a[Math.min(a.length - 1, Math.floor(a.length * p))];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const spin = (ms) => { const end = performance.now() + ms; while (performance.now() < end); };
const report = [];
for (const gapMs of gaps) {
  const trialsOut = [];
  for (let k = 0; k < trials; k++) {
    const t = [];
    for (let i = 0; i < n; i++) {
      if (gapMs > 0 && mode === "spin") spin(gapMs);
      else if (gapMs > 0) await sleep(gapMs);
      const a = performance.now();
      await py.run("import channels\nchannels.channelCount()");
      t.push((performance.now() - a) * 1000);
    }
    t.sort((x, y) => x - y);
    trialsOut.push({
      median_us: +pct(t, 0.5).toFixed(2),
      p90_us: +pct(t, 0.9).toFixed(2),
      over150_ratio: +(t.filter((x) => x > 150).length / t.length).toFixed(3),
    });
  }
  report.push({ gap_ms: gapMs, trials: trialsOut });
}
console.log(JSON.stringify({ n, trials, mode, load: fs.readFileSync("/proc/loadavg", "utf8").trim(), report }));
await py.terminate();
