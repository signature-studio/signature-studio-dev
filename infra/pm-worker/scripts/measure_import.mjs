// 合成データで取り込み本文の大きさと Worker の検証 (parseVmState) を測る (#2799)。
// 使い方 (リポジトリの root で): node --experimental-strip-types --no-warnings infra/pm-worker/scripts/measure_import.mjs [出力 dir]
// 合成データは issue 番号 11〜90 の連番 80 件 (launched・relaunch・pm_art の各 80 件)。出力 dir の既定は infra/pm-worker/work/import (gitignore)。
// 3 つの本文を作って表にする: jq -n (旧手順の整形)・jq -cn (README の式)・build_import.mjs。
// 実 VM の値ではない。

import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { buildImport, serialize } from "./build_import.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const dir = resolve(process.argv[2] ?? join(here, "..", "work", "import"));
const NOW = Date.parse("2026-10-14T12:00:00Z");
const { parseVmState } = await import(pathToFileURL(join(here, "..", "src", "vmstate.ts")).href);

const COMBOS = ["oc_artifacts: fl-win64", "oc_artifacts: fl-win64 plugins-ott", "oc_artifacts: fl-win64 plugins-ott toolchain-emsdk"];
const kinds = { relaunch_mixed: 0, relaunch_bracket: 0, pm_art_bracket: 0, pm_art_disallowed: 0 };
const launched = {};
const relaunch = {};
const pm_art = {};
for (let n = 11; n <= 90; n++) {
  launched[n] = `2026-10-14T11:${String(n % 60).padStart(2, "0")}:00.000000+00:00`;
  if (n % 5 === 0) {
    relaunch[n] = { count: 1 + (n % 3), art: "oc_artifacts: none fl-win64" };
    kinds.relaunch_mixed++;
  } else if (n % 6 === 0) {
    relaunch[n] = { count: 1, art: "oc_artifacts: fl-win64 plugins-ott（kilohearts の確認は後で）" };
    kinds.relaunch_bracket++;
  } else relaunch[n] = { count: 0, art: null };
  const at = "2026-10-13T10:00:00Z";
  if (n === 90) {
    pm_art[n] = { at, line: "oc_artifacts: fetchsh" };
    kinds.pm_art_disallowed++;
  } else if (n % 4 === 0) {
    pm_art[n] = { at, line: "oc_artifacts: fl-win64 plugins-ott (解析用の素材。PM が指定)" };
    kinds.pm_art_bracket++;
  } else pm_art[n] = { at, line: COMBOS[n % 3] };
}
const phase = { review_only: false, open_prs: 4, since: "2026-10-14T10:00:00.123456+00:00" };

mkdirSync(dir, { recursive: true });
const p = (name) => join(dir, name);
writeFileSync(p("launched.json"), JSON.stringify(launched, null, 2));
writeFileSync(p("relaunch.json"), JSON.stringify(relaunch, null, 2));
writeFileSync(p("issues_state.json"), JSON.stringify({ pm_art }, null, 2));
writeFileSync(p("export.json"), JSON.stringify({ phase }, null, 2));

const read = (name) => JSON.parse(readFileSync(p(name), "utf8"));
const JQ_PROGRAM = "{launched: $l[0], relaunch: $r[0], phase: $e[0].phase, pm_art: $s[0].pm_art}";
const jq = (flag) =>
  execFileSync(
    "jq",
    [flag, "--slurpfile", "l", p("launched.json"), "--slurpfile", "r", p("relaunch.json"), "--slurpfile", "e", p("export.json"), "--slurpfile", "s", p("issues_state.json"), JQ_PROGRAM],
    { encoding: "utf8" },
  );
const logs = [];
const built = serialize(
  buildImport({ launched: read("launched.json"), relaunch: read("relaunch.json"), state: read("issues_state.json"), phase: read("export.json").phase }, (m) => logs.push(m)),
);
const bodies = [
  ["jq -n (整形・旧手順)", "import_jq_n.json", jq("-n")],
  ["jq -cn (README の式)", "import_jq_cn.json", jq("-cn")],
  ["build_import.mjs", "import_build.json", built],
];

console.log(`合成データ (dir: ${dir}): issue 11〜90 の 80 件`);
console.log(`  relaunch の none と素材名の混在 ${kinds.relaunch_mixed} 件・括弧書き ${kinds.relaunch_bracket} 件 / pm_art の括弧書き ${kinds.pm_art_bracket} 件・許可外 ${kinds.pm_art_disallowed} 件 (pm_art の許可外は #90)`);
console.log(`  build_import.mjs の標準エラー: ${logs.length} 行`);
console.log("");
console.log("| 本文 | バイト (ファイルに書いた量) | parseVmState | 問題数 | うち relaunch | うち pm_art |");
console.log("|---|---|---|---|---|---|");
let exit = 0;
for (const [label, file, text] of bodies) {
  writeFileSync(p(file), text);
  const bytes = Buffer.byteLength(text, "utf8");
  const r = parseVmState(JSON.parse(text), NOW);
  const problems = r.ok ? [] : r.problems;
  const count = (prefix) => problems.filter((m) => m.startsWith(prefix)).length;
  const verdict = r.ok ? "ok" : "400";
  if (label.startsWith("build") && !r.ok) exit = 1;
  console.log(`| ${label} | ${bytes} | ${verdict} | ${problems.length} | ${count("relaunch.")} | ${count("pm_art.")} |`);
}
process.exitCode = exit;
