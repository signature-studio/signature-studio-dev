// flapi 往復コスト計測 (Worker -> SAB RPC -> mock engine)。N 回ずつ繰り返し µs/呼出し を表示する。
//   node tests/rtt_bench.mjs     (前提: build_flpy.sh 済み。共有環境では負荷で変動するため複数回の値を見る)
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const py = await FlPython.create({ flpyUrl: new URL("dist/flpy.js", root), engine: createMockEngine(), ids, files: {}, onStdout() {}, onStderr() {} });
await py.run("import fl_rt\nfl_rt.install_flapi()");
const meas = async (n) => {
  const t = performance.now();
  await py.run(`import channels\nfor _ in range(${n}): channels.channelCount()`);
  return ((performance.now() - t) * 1000) / n;
};
const out = [];
for (const n of [500, 2000, 2000, 20000, 20000, 20000]) out.push({ n, us_per_call: +(await meas(n)).toFixed(1) });
console.log(JSON.stringify(out));
await py.terminate();
