// 規則 A の実データ dry-run (#2336)。REST の生 JSON を Worker の経路 (applyEvent → detectRuleA) に通し、候補を JSON で出す。読み取りのみ。
// usage: node --experimental-strip-types infra/pm-worker/scripts/rule_a_dryrun.ts <dir>
//   <dir> には tools/pm/rule_a_realcheck.sh が取った issues_open.json・pulls_open.json・pulls_closed.json・blocked.jsonl がある。
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { detectRuleA } from "../src/autoclose.ts";
import { EMPTY_STATE, applyEvent, type PmState } from "../src/webhook.ts";

const dir = process.argv[2];
if (!dir) throw new Error("usage: rule_a_dryrun.ts <dir>");
const read = (f: string) => JSON.parse(readFileSync(join(dir, f), "utf8"));
const issues: any[] = read("issues_open.json").flat().filter((i: any) => !i.pull_request);
const prsOpen: any[] = read("pulls_open.json").flat();
const prsClosed: any[] = read("pulls_closed.json").flat();
const blocked: Array<{ k: number; v: number[] }> = readFileSync(join(dir, "blocked.jsonl"), "utf8")
  .split("\n")
  .filter(Boolean)
  .map((l) => JSON.parse(l));

// Worker の保存経路 (webhook と同じ applyEvent) で状態を作る。closed PR は窓 (24 時間) の有無で二通り作る。
const build = (closed: any[]): PmState => {
  let s: PmState = structuredClone(EMPTY_STATE);
  for (const issue of issues) s = applyEvent(s, "issues", { issue }, "bot", [], "rev");
  for (const pull_request of [...closed, ...prsOpen]) s = applyEvent(s, "pull_request", { pull_request }, "bot", [], "rev");
  for (const b of blocked) s.blockedBy[String(b.k)] = [...b.v].sort((x, y) => x - y);
  return s;
};
const cut = Date.now() - 24 * 3_600_000;
const key = (t: { n: number; mergedPr: number; child: number }) => [t.n, t.mergedPr, t.child];
console.log(
  JSON.stringify({
    full_history: detectRuleA(build(prsClosed)).map(key),
    window_24h: detectRuleA(build(prsClosed.filter((p) => Date.parse(p.updated_at) >= cut))).map(key),
  }),
);
