// PY-102 (#2883) の §3-2 再現: 表の個数 (kwsig.max) の呼出しを wasm provider に流し、dispatch の code を出す。
//   node tests/sig_arity_probe.mjs     (前提: provider/build.sh 済み・analysis/flapi/flapi_table.json)
import fs from "node:fs";
import { createWasmEngine } from "../host/fl_provider.mjs";
const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const table = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_table.json", root)));
const eng = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const names = "channels.getStepParam channels.soloChannel device.midiOutMsg mixer.armTrack mixer.enableTrack mixer.getTrackName mixer.selectTrack patterns.clonePattern playlist.muteTrack playlist.selectTrack plugins.getColor plugins.getParamValueString screen.addMeter screen.addTextLine screen.animateText screen.blank screen.drawRect screen.drawText screen.eraseRect screen.findTextLine screen.removeTextLine screen.setScreenActiveCounter screen.unBlank".split(" ");
const out = [];
for (const n of names) {
  const [m, f] = n.split(".");
  const e = table.modules[m][f];
  const mx = e.kwsig.max;
  let args = Array.from({ length: mx }, (_, i) => (i === 0 ? 0 : 1));
  let r;
  try { eng.call(n, args); r = "ok"; } catch (x) { r = `code ${x.flCode}`; }
  out.push(`${n} max=${mx} np=${e.sig ? e.sig.params.length : "-"} 呼出し${mx}個 -> ${r}`);
}
console.log(out.join("\n"));
