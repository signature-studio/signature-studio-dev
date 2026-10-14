// launch の停止の規則 (#2795) の変異テスト。規則を 1 か所ずつ壊し、test/halt*.test.ts が落ちることを確かめる。
// 壊すのは src/ の 1 箇所だけで、必ず元に戻す (finally)。1 つでも落ちない変異があれば終了コード 1。
// 実行: npm run test:mutation (infra/pm-worker で)。
import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const TESTS = ["test/halt.test.ts", "test/halt_engine.test.ts"];

const MUTANTS = [
  { name: "既定の IMPORT_REQUIRED を 0 扱い (取り込み必須) に戻す", file: "src/config.ts", from: 'importRequired: env.IMPORT_REQUIRED === "1"', to: 'importRequired: env.IMPORT_REQUIRED !== "0"' },
  { name: "overdue の閾値を 16 分にする", file: "src/halt.ts", from: "export const HALT_OVERDUE_MS = 15 * 60_000;", to: "export const HALT_OVERDUE_MS = 16 * 60_000;" },
  { name: "通知の閾値を 29 分にする", file: "src/halt.ts", from: "export const HALT_NOTIFY_MS = 30 * 60_000;", to: "export const HALT_NOTIFY_MS = 29 * 60_000;" },
  { name: "overdue から着手待ち (ready) の条件を外す", file: "src/halt.ts", from: "ready > 0 && room > 0", to: "room > 0" },
  { name: "止まっている間に起点を毎回今にする", file: "src/halt.ts", from: "return { ...prev, reasons };", to: "return { since: now, reasons };" },
  { name: "条件が 0 になっても区間を消さない", file: "src/halt.ts", from: "if (reasons.length === 0) return undefined;", to: "if (reasons.length === 0) return prev;" },
  { name: "同じ停止区間の重複抑止 (notifiedAt) を外す", file: "src/halt.ts", from: "!halt.notifiedAt && ", to: "" },
];

const runTests = () => {
  const r = spawnSync(process.execPath, ["--experimental-strip-types", "--no-warnings", "--test", ...TESTS], { cwd: root, encoding: "utf8", timeout: 300_000 });
  return r.status === 0;
};

if (!runTests()) {
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
  let killed;
  try {
    writeFileSync(path, original.replace(m.from, m.to));
    killed = !runTests();
  } finally {
    writeFileSync(path, original);
  }
  console.log(`${killed ? "killed  " : "SURVIVED"}  ${m.name}`);
  if (!killed) survived++;
}

console.log(`mutants=${MUTANTS.length} survived=${survived}`);
process.exit(survived === 0 ? 0 : 1);
