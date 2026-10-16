// oc:no-pr の再投入の規則 (#3185: 新しい素材の無い artifact を unknown と同じく 1 回だけ再投入し、その後は oc-pm に回す) の変異テスト。
// 規則を 1 か所ずつ壊し、test/engine.test.ts・test/launch.test.ts・test/killed.test.ts のいずれかが落ちることを確かめる。
// 壊すのは src/ の 1 箇所だけで、必ず元に戻す (finally)。1 つでも落ちない変異があれば終了コード 1。落ちたテスト名を変異ごとに出す。
// 実行: npm run test:mutation (infra/pm-worker で)。
import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const TESTS = ["test/engine.test.ts", "test/launch.test.ts", "test/killed.test.ts", "test/status.test.ts", "test/launch_holds.test.ts"];

const MUTANTS = [
  { name: "報告の素材を前回の行と比べない (常に新しい素材ありとみなす)", file: "src/engine.ts", from: "return addArts(base, neededArtsOf(", to: 'return addArts("oc_artifacts: none", neededArtsOf(' },
  { name: "cooldown を外す (noPr の経路)", file: "src/engine.ts", from: "} else if (nowMs - this.lastAct(n) < cool(n)) {", to: "} else if (false) {" },
  { name: "再投入の計数 (count) を数えない", file: "src/engine.ts", from: "count: c.count + 1,", to: "count: c.count," },
  { name: "unknown の枠を数えない (fallback を何度でも出す)", file: "src/engine.ts", from: 'unknown: c.unknown + (p.np === "unknown" ? 1 : 0),', to: "unknown: c.unknown," },
  { name: "unknown の再投入 (1 回目) を外す (#2334 の unknown は再着手する)", file: "src/engine.ts", from: '} else if (reason === "unknown" && c.unknown === 0) {', to: "} else if (false) {" },
  { name: "unknown の枠の上限を外す (fallback の c.unknown === 0 を外す)", file: "src/engine.ts", from: '} else if (reason === "artifact" && c.unknown === 0) {', to: '} else if (reason === "artifact" && c.unknown < 99) {' },
  { name: "再投入後の素材なし artifact を oc-pm に渡さない", file: "src/pm.ts", from: "const artDone = oc.reason === \"artifact\" && !!o.artSpent?.(i.number);", to: "const artDone = false;" },
  { name: "上限に達した素材なし artifact を oc-pm に渡さない (artSpent の上限の枝を外す)", file: "src/engine.ts", from: "this.noPrState(n).unknown >= 1 || this.noPrState(n).count >= NO_PR_MAX_RELAUNCH", to: "this.noPrState(n).unknown >= 1" },
  { name: "stopped の判定根拠 (run-outcome) を reason なしの語にする (#5234)", file: "src/engine.ts", from: "stopBasis.set(n, `run-outcome reason=${reason}`);", to: 'stopBasis.set(n, "run-outcome");' },
  { name: "再確認の 1 行を本文から外す", file: "src/launch.ts", from: 'if (l === "{recheck}") return recheck ? [RECHECK_LINE] : [];', to: 'if (l === "{recheck}") return [];' },
];

const runTests = () => {
  const r = spawnSync(process.execPath, ["--experimental-strip-types", "--no-warnings", "--test", ...TESTS], { cwd: root, encoding: "utf8", timeout: 300_000 });
  const failed = [...(r.stdout ?? "").matchAll(/^not ok \d+ - (.+)$/gm)].map((m) => m[1].slice(0, 70));
  return { ok: r.status === 0, failed };
};

const base = runTests();
if (!base.ok) {
  console.error("baseline: 元の規則でテストが落ちています。変異テストを始めません");
  process.exit(1);
}

let survived = 0;
for (const m of MUTANTS) {
  const path = join(root, m.file);
  const original = readFileSync(path, "utf8");
  const hits = original.split(m.from).length - 1;
  if (hits !== 1) {
    console.error(`skip: ${m.name}: 対象の文字列が ${hits} 件 (1 件であること)`);
    survived++;
    continue;
  }
  let res;
  try {
    writeFileSync(path, original.replace(m.from, m.to));
    res = runTests();
  } finally {
    writeFileSync(path, original);
  }
  const killed = !res.ok;
  console.log(`${killed ? "killed  " : "SURVIVED"}  ${m.name}`);
  for (const t of res.failed) console.log(`          falls: ${t}`);
  if (!killed) survived++;
}

console.log(`mutants=${MUTANTS.length} survived=${survived}`);
process.exit(survived === 0 ? 0 : 1);
