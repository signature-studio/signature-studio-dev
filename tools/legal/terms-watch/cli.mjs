#!/usr/bin/env node
// 各社規約の差分監視 CLI (LGL-5, #88)
//   node tools/legal/terms-watch/cli.mjs [check] [--only id,id] [--fl-dir dir] [--plugins-dir dir] [--allow-skip|--strict] [--no-write] [--json out.json]
//                                         [--sources f] [--ledger f] [--md f] [--snapshots dir]
//   node tools/legal/terms-watch/cli.mjs ack <id...|all> [--ledger f] [--md f]   # 差分をレビュー済みにする
// 終了コード: 0 全件一致 / 1 差分あり or 未レビュー変更が残存 / 2 引数不正 / 3 検証不能 (取得失敗・素材なし)
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { FL_WIN64_DIR, PLUGINS_DIR, REPO_ROOT } from "../../shared/paths.mjs";
import { ackDocs, exitCodeFor, loadLedger, renderLedgerMd, runCheck, serializeLedger } from "./lib.mjs";

const here = import.meta.dirname;
const [first, ...restAll] = process.argv.slice(2);
const cmd = first && !first.startsWith("--") ? first : "check";
const rest = first && !first.startsWith("--") ? restAll : process.argv.slice(2);
const opt = (name) => { const i = rest.indexOf(`--${name}`); return i >= 0 ? rest[i + 1] : undefined; };
const flag = (name) => rest.includes(`--${name}`);
const usage = () => {
  console.error("usage: cli.mjs [check] [--only id,id] [--fl-dir dir] [--plugins-dir dir] [--allow-skip|--strict] [--no-write] [--json out] [--sources f] [--ledger f] [--md f] [--snapshots dir]\n       cli.mjs ack <id...|all> [--ledger f] [--md f]");
  process.exit(2);
};

const sourcesFile = path.resolve(opt("sources") ?? path.join(here, "sources.json"));
const ledgerFile = path.resolve(opt("ledger") ?? path.join(REPO_ROOT, "docs/LEGAL_TERMS_LEDGER.json"));
const mdFile = path.resolve(opt("md") ?? path.join(REPO_ROOT, "docs/LEGAL_TERMS_LEDGER.md"));
const snapDir = path.resolve(opt("snapshots") ?? path.join(here, "work/snapshots"));
const now = process.env.TERMS_WATCH_NOW ?? new Date().toISOString();
const sources = JSON.parse(readFileSync(sourcesFile, "utf8"));
const ledger = loadLedger(ledgerFile);

const save = () => {
  mkdirSync(path.dirname(ledgerFile), { recursive: true });
  writeFileSync(ledgerFile, serializeLedger(ledger));
  writeFileSync(mdFile, renderLedgerMd(ledger, sources));
};

if (cmd === "ack") {
  const ids = rest.filter((a, i) => !a.startsWith("--") && !rest[i - 1]?.startsWith("--"));
  if (!ids.length) usage();
  try {
    const done = ackDocs(ledger, ids, now);
    save();
    console.log(`terms-watch: ack ${done.length ? done.join(", ") : "(レビュー待ち無し)"}`);
  } catch (e) {
    console.error(`terms-watch: ${e.message}`);
    process.exit(2);
  }
} else if (cmd === "check") {
  const only = opt("only")?.split(",").filter(Boolean) ?? null;
  if (only) for (const id of only) if (!sources.some((s) => s.id === id)) { console.error(`terms-watch: 未知の id ${id}`); process.exit(2); }
  const t0 = Date.now();
  const results = await runCheck({ sources, ledger, ctx: { flDir: opt("fl-dir") ?? FL_WIN64_DIR, pluginsDir: opt("plugins-dir") ?? PLUGINS_DIR }, now, snapshotDir: snapDir, only });
  const code = exitCodeFor(results, { allowSkip: flag("allow-skip"), strict: flag("strict") });
  const old = new Map(results.filter((r) => r.status === "CHANGED").map((r) => [r.id, r.previous.sha256]));
  if (!flag("no-write")) save();
  for (const r of results) {
    const extra = r.detail ? ` — ${r.detail}` : r.status === "CHANGED" ? ` ${r.previous.sha256.slice(0, 12)}… → ${r.sha256.slice(0, 12)}… (版表記 ${r.previous.version ?? "なし"} → ${r.version ?? "なし"})` : ` ${r.sha256?.slice(0, 12)}… ${r.chars} chars${r.version ? ` 版表記 ${r.version}` : ""}`;
    console.log(`${r.status.padEnd(9)} ${r.id}${extra}`);
  }
  for (const [id, prev] of old) {
    const a = path.join(snapDir, id, `${prev}.txt`);
    const b = path.join(snapDir, id, `${results.find((r) => r.id === id).sha256}.txt`);
    if (existsSync(a) && existsSync(b)) {
      const d = spawnSync("diff", ["-u", a, b], { encoding: "utf8" });
      console.log(`--- diff ${id} (先頭 60 行) ---\n${d.stdout.split("\n").slice(0, 60).join("\n")}`);
    } else console.log(`(diff 不可: ${id} の旧版スナップショットが ${snapDir} に無い)`);
  }
  if (opt("json")) writeFileSync(opt("json"), JSON.stringify({ code, seconds: (Date.now() - t0) / 1000, results }, null, 1));
  const c = (s) => results.filter((r) => r.status === s).length;
  console.log(`terms-watch: exit ${code} (UNCHANGED ${c("UNCHANGED")} / NEW ${c("NEW")} / CHANGED ${c("CHANGED")} / PENDING ${c("PENDING")} / SKIP ${c("SKIP")} / ERROR ${c("ERROR")}) ${(Date.now() - t0) / 1000}s`);
  if (c("CHANGED") || c("PENDING")) console.error("terms-watch: 規約の差分あり。docs/LEGAL.md を見直し、確認後に `pnpm terms-watch ack <id|all>` でレビュー済みにする");
  process.exit(code);
} else usage();
