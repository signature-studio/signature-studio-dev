#!/usr/bin/env node
// release guard CLI (LGL-2)
//   node tools/legal/release-guard/cli.mjs build --from <dir|file> [--from ...] [--manifest <tools/assets manifest.json> ...] [--out <dir>]
//   node tools/legal/release-guard/cli.mjs scan  --src <dist> [--src ...] [--manifest <deploy manifest.json> ...] [--list <paths.txt> [--root <dir>]]
//                                                [--denylist <dir>] [--allowlist <file>] [--json <out.json>]
// scan は deny-list 一致で終了コード 6、deny-list 欠落 4、不正 5、引数不正 2。
import { writeFileSync } from "node:fs";
import path from "node:path";
import {
  buildDenylist, collectEntries, DEFAULT_ALLOWLIST, DEFAULT_DENYLIST, DenylistMissing, formatViolations, loadAllowlist, loadDenylist, scanEntries,
} from "./lib.mjs";

const [cmd, ...rest] = process.argv.slice(2);
const multi = (name) => rest.flatMap((a, i) => (a === `--${name}` ? [rest[i + 1]] : []));
const one = (name, d) => multi(name).at(-1) ?? d;
const usage = () => {
  console.error("usage: cli.mjs build --from <dir>... [--manifest m.json...] [--out dir] [--window N --mask 0x3ff]\n       cli.mjs scan --src <dist>... [--manifest m.json...] [--list f --root d] [--denylist dir] [--allowlist f] [--json out]");
  process.exit(2);
};

if (cmd === "build") {
  const t0 = Date.now();
  const params = {};
  if (one("window")) params.window = Number(one("window"));
  if (one("mask")) params.mask = Number(one("mask"));
  const out = path.resolve(one("out", DEFAULT_DENYLIST));
  const r = await buildDenylist({ from: multi("from"), manifests: multi("manifest"), out, params, log: (s) => console.error(s) });
  console.log(JSON.stringify({ out, ...r, seconds: (Date.now() - t0) / 1000 }, null, 1));
} else if (cmd === "scan") {
  const src = multi("src");
  const manifests = multi("manifest");
  const list = one("list");
  if (!src.length && !manifests.length && !list) usage();
  const t0 = Date.now();
  let dl;
  try { dl = loadDenylist(path.resolve(one("denylist", process.env.RELEASE_GUARD_DENYLIST ?? DEFAULT_DENYLIST))); } catch (e) {
    console.error(`release-guard: ${e.message}`);
    process.exit(e instanceof DenylistMissing ? 4 : 5);
  }
  const allow = loadAllowlist(path.resolve(one("allowlist", process.env.RELEASE_GUARD_ALLOWLIST ?? DEFAULT_ALLOWLIST)));
  const entries = collectEntries({ src, manifests, list, root: one("root") });
  if (!entries.length) { console.error("release-guard: 走査対象が 0 件 (fail-closed)"); process.exit(2); }
  const rep = await scanEntries(entries, dl, allow);
  rep.seconds = (Date.now() - t0) / 1000;
  if (one("json")) writeFileSync(one("json"), JSON.stringify(rep, null, 1));
  if (rep.failed) {
    console.error(formatViolations(rep));
    process.exit(6);
  }
  console.log(`release-guard: PASS ${rep.files} files ${rep.bytes} B deny-list=${rep.denylist} ${rep.seconds}s${rep.suppressed.length ? ` allow-list 許容 ${rep.suppressed.length} files` : ""}`);
} else usage();
