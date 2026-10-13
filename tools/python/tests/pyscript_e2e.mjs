// .pyscript ローダ + flpianoroll の回帰テスト (PY-5 / #79)。node 実行。シナリオ本体は tests/pyscript_scenarios.mjs (Chrome 版 PY-11 / #466 と共通)。
//   FL_WIN64_DIR=<dir> node tests/pyscript_e2e.mjs [--dump <out.json>]      (前提: build_flpy.sh 済み = dist/flpy.js)
//   --dump: results/outputs を JSON で保存 (tests/pyscript_compare.py の入力。node と Chrome の出力一致比較用)
//   --export-scripts <out.json>: 特定した FL 同梱スクリプト本文を保存 (Chrome 版が fetch する。work/ 配下に置く = gitignore。FL 由来物なので commit しない)
// FL 同梱の .pyscript は利用者の FL インストール (FL_WIN64_DIR/extracted/block*_DATA.bin) から実行時に供給する。
// リポジトリには同梱しない。ブロック名は元ファイル名を持たないため、内容 (ScriptDialog の題名 / 関数名) で特定する。
import fs from "node:fs";
import path from "node:path";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { FL_WIN64_DIR } from "../../shared/paths.mjs";
import { runScenarios } from "./pyscript_scenarios.mjs";

const root = new URL("../", import.meta.url);
const arg = (k) => { const i = process.argv.indexOf(k); return i >= 0 ? process.argv[i + 1] : null; };
const t0 = Date.now();

const dir = path.join(FL_WIN64_DIR, "extracted");
if (!fs.existsSync(dir)) { console.error(`FL_WIN64_DIR/extracted not found: ${dir}`); process.exit(2); }
const blocks = fs.readdirSync(dir).filter((f) => /^block\d+_DATA\.bin$/.test(f));
const texts = new Map();
for (const f of blocks) {
  const p = path.join(dir, f);
  if (fs.statSync(p).size > 40000) continue;
  const b = fs.readFileSync(p);
  if (b.includes(0)) continue;
  const s = b.toString("utf8");
  if (/def createDialog|flpianoroll|enveditor|def (filleach|rerollLS|flrInit)|def mapToRange/.test(s)) texts.set(f, s);
}
const find = (re, { not } = {}) => {
  const hit = [...texts].filter(([, s]) => re.test(s) && !(not && not.test(s)));
  if (hit.length !== 1) throw new Error(`script ${re}: ${hit.length} matches`);
  return hit[0];
};
const PR = {
  Euclidean: find(/ScriptDialog\('Euclidean'/),
  Humanize: find(/ScriptDialog\("Humanize Tool"/),
  Repeater: find(/ScriptDialog\("Note Repeater\/Sprinkler"/),
  Selector: find(/ScriptDialog\("Condition-based Note Selection"/),
  Arpeggiator: find(/ScriptDialog\("Randomized Arpeggiator"/),
};
const REMOTE = {
  filleach: find(/def filleach/), rerollLSloop: find(/def rerollLSloop/), rerollLSsample: find(/def rerollLSsample/),
  rerollLSsteps: find(/def rerollLSsteps/), flrInit: find(/def flrInit/),
};
const AUDIO = [...texts].filter(([, s]) => /^from enveditor import/m.test(s) && !s.startsWith("Edison Script Reference"));

const exportTo = arg("--export-scripts");
if (exportTo) {
  fs.mkdirSync(path.dirname(exportTo), { recursive: true });
  fs.writeFileSync(exportTo, JSON.stringify({ PR, REMOTE, AUDIO }));
  console.log(`exported scripts -> ${exportTo}`);
}

const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const inv = JSON.parse(fs.readFileSync(new URL("analysis/scripts_inventory.json", root)));
const { results, outputs } = await runScenarios({ FlPython, createMockEngine, PR, REMOTE, AUDIO, ids, inv, flpyUrl: new URL("dist/flpy.js", root) });

const pass = results.filter((r) => r.ok).length;
const sec = ((Date.now() - t0) / 1000).toFixed(1);
const summary = { total: results.length, pass, fail: results.length - pass, seconds: Number(sec) };
console.log(JSON.stringify(summary));
for (const r of results) console.log(r.ok ? "PASS" : "FAIL", r.name);
const dump = arg("--dump");
if (dump) { fs.mkdirSync(path.dirname(dump), { recursive: true }); fs.writeFileSync(dump, JSON.stringify({ env: `node ${process.version}`, summary, results, outputs })); }
process.exit(pass === results.length ? 0 : 1);
