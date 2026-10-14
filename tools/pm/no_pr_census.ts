// #2652 の検算: 全体同期 (fullSync) と同じ入力 (open issue の全件・24 時間窓のコメント) を REST から集め、
// infra/pm-worker の純関数 (applyEvent・detectPm) に通して、oc:no-pr の検出の内訳を数える。読み取りだけ (gh api GET)。
// 使い方: cd <repo> && node --experimental-strip-types --no-warnings tools/pm/no_pr_census.ts [窓の時間数=24]
import { execFileSync } from "node:child_process";
import { applyEvent, EMPTY_STATE, type PmState } from "../../infra/pm-worker/src/webhook.ts";
import { detectPm, HOLD_LABELS, NO_PR_LABEL } from "../../infra/pm-worker/src/pm.ts";

const R = "signature-studio/signature-studio-dev";
const BOT = "opencode-for-signature-studio[bot]";
const REV = "oc-reviewer-for-signature-studio[bot]";
const PM_LOGINS = ["pycabbage"];
const WINDOW_H = Number(process.argv[2] ?? 24);
const MAX_PAGES = 150;

const api = (path: string): any => JSON.parse(execFileSync("gh", ["api", "-X", "GET", path], { encoding: "utf8", maxBuffer: 1 << 28 }));

const issues: any[] = [];
for (let p = 1; ; p++) {
  const page = api(`repos/${R}/issues?state=open&per_page=100&page=${p}`);
  if (!page.length) break;
  issues.push(...page.filter((i: any) => !i.pull_request));
  if (page.length < 100) break;
}

const mine = new Set([BOT, REV, ...PM_LOGINS]);
const since = Date.now() - WINDOW_H * 3_600_000;
const comments: any[] = [];
let truncated = false;
for (let p = 1; ; p++) {
  if (p > MAX_PAGES) {
    truncated = true;
    break;
  }
  const page = api(`repos/${R}/issues/comments?sort=created&direction=desc&per_page=100&page=${p}`);
  if (!page.length) break;
  let stop = false;
  for (const c of page) {
    if (Date.parse(c.created_at) < since) {
      stop = true;
      break;
    }
    comments.push({ id: c.id, issue_url: c.issue_url, created_at: c.created_at, user: { login: c.user?.login }, author_association: c.author_association, body: mine.has(c.user?.login) ? c.body : "" });
  }
  if (stop || page.length < 100) break;
}

let s: PmState = EMPTY_STATE;
for (const i of issues) s = applyEvent(s, "issues", { issue: i }, BOT, PM_LOGINS, REV);
for (const c of comments) {
  const n = Number(String(c.issue_url).split("/").pop());
  s = applyEvent(s, "issue_comment", { action: "created", comment: c, issue: { number: n } }, BOT, PM_LOGINS, REV);
}

const bots = [BOT, REV];
const detected = detectPm(s, { bots, npCount: () => 0 }).filter((t) => t.kind === "no_pr");
const detectedSet = new Set(detected.map((t) => t.ref));

const noPr = issues.filter((i) => i.state === "open" && i.labels.some((l: any) => l.name === NO_PR_LABEL));
const byReason: Record<string, number> = {};
const why: Record<string, number> = {};
const examples: Record<string, number[]> = {};
for (const i of noPr) {
  const sig = s.sig[String(i.number)];
  const oc = sig?.outcome;
  const reason = oc?.reason ?? "(no outcome in window)";
  byReason[reason] = (byReason[reason] ?? 0) + 1;
  if (!oc) continue;
  const st = s.issues[String(i.number)];
  let w: string;
  if (detectedSet.has(i.number)) w = "detected";
  else if (!st || !(st.assoc && ["MEMBER", "OWNER", "COLLABORATOR"].includes(st.assoc)) && !(st.authorType === "Bot" && bots.includes(st.author ?? ""))) w = "author-not-allowed";
  else if (i.labels.some((l: any) => HOLD_LABELS.includes(l.name))) w = "hold-label";
  else if (sig?.pmAt && Date.parse(sig.pmAt) > Date.parse(oc.at)) w = "pm-answered-after";
  else if (reason !== "split" && reason !== "stop") w = `reason=${reason}`;
  else w = "other";
  why[w] = (why[w] ?? 0) + 1;
  (examples[w] ??= []).push(i.number);
}

const out = {
  measured_at: new Date().toISOString(),
  window_h: WINDOW_H,
  open_issues: issues.length,
  comments_in_window: comments.length,
  comments_truncated: truncated,
  open_no_pr: noPr.length,
  no_pr_by_reason: byReason,
  no_pr_outcome_breakdown: why,
  detected_no_pr: detected.map((t) => t.ref),
  examples: Object.fromEntries(Object.entries(examples).map(([k, v]) => [k, v.slice(0, 12)])),
};
console.log(JSON.stringify(out, null, 2));
