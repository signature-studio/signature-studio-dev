// webhook 受信の純関数。署名を検証してから状態を変える (未検証の入力では状態を一切変えない)。
// 永続化 (Durable Object / SQLite) は呼び出し側の責務。ここは state を受け取り、次の state を返すだけ。
import { verifySignature } from "./hmac.ts";

export const WEBHOOK_EVENTS = [
  "issues",
  "issue_comment",
  "issue_dependencies",
  "pull_request",
  "pull_request_review",
  "workflow_run",
] as const;
export type WebhookEvent = (typeof WEBHOOK_EVENTS)[number];

export interface IssueState {
  number: number;
  title: string;
  labels: string[];
  body: string;
  state: "open" | "closed";
  updatedAt: string;
  // issue_dependencies_summary.total_blocked_by (blocker の一覧は PmState.blockedBy)
  blockedByCount: number;
}
export interface PrState {
  number: number;
  state: "open" | "closed";
  merged: boolean;
  draft: boolean;
  ref: string;
  title: string;
  body: string;
  updatedAt: string;
}
export interface RunState {
  id: number;
  event: string;
  title: string;
  status: string;
  conclusion: string | null;
  updatedAt: string;
}
export interface BotComment {
  issueNumber: number;
  at: string;
  body: string;
}
export interface PmState {
  issues: Record<string, IssueState>;
  prs: Record<string, PrState>;
  runs: Record<string, RunState>;
  // issue ごとの最後の bot コメント (分類の bot_last に相当)
  botLast: Record<string, BotComment>;
  // PM のコメントに書かれた最後の `oc_artifacts:` 行 (分類の pm_art に相当)
  pmArt: Record<string, { at: string; line: string }>;
  // issue dependencies (blocked_by) の blocker 番号 (open/closed 問わず。分類側で open だけに絞る)
  blockedBy: Record<string, number[]>;
  // PM (人間の PAT / PM App) が `/oc` コメントで着手を依頼した最後の時刻 (分類の launched に相当)
  launchedAt: Record<string, string>;
}

export const EMPTY_STATE: PmState = { issues: {}, prs: {}, runs: {}, botLast: {}, pmArt: {}, blockedBy: {}, launchedAt: {} };

export interface WebhookInput {
  secret: string;
  event: string | null;
  signature: string | null | undefined;
  body: string;
  botLogin: string;
  // PM のログイン名 (人間の PAT と PM App の bot)。`oc_artifacts:` 行の取得に使う。省略時は取得しない。
  pmLogins?: string[];
  // 指定すると、payload.repository.full_name が一致しない配送は無視する (別 repo の配送を状態に混ぜない)。
  repo?: string;
}

export type WebhookResult =
  | { status: 401; state: PmState; reason: string }
  | { status: 202; state: PmState; reason: "ignored" | "applied" };

type Json = Record<string, any>;

function isEvent(e: string | null): e is WebhookEvent {
  return (WEBHOOK_EVENTS as readonly string[]).includes(e ?? "");
}

// 同じ番号の既存より古い更新は無視する (再送・順不同配送への耐性)。
function newer(prev: { updatedAt: string } | undefined, at: string): boolean {
  return !prev || Date.parse(at) >= Date.parse(prev.updatedAt);
}

function applyIssue(s: PmState, p: Json): PmState {
  const i = p.issue;
  if (!i || "pull_request" in i) return s;
  const k = String(i.number);
  if (!newer(s.issues[k], i.updated_at)) return s;
  const closed = i.state === "closed";
  const summary = i.issue_dependencies_summary?.total_blocked_by;
  const next: IssueState = {
    number: i.number,
    title: i.title,
    // closed の issue は分類に使わない。番号・状態・更新時刻だけ残す (順不同配送の判定用)。
    labels: closed ? [] : (i.labels ?? []).map((l: Json) => l.name),
    body: closed ? "" : i.body ?? "",
    state: closed ? "closed" : "open",
    updatedAt: i.updated_at,
    blockedByCount: Number.isInteger(summary) ? summary : (s.issues[k]?.blockedByCount ?? 0),
  };
  return { ...s, issues: { ...s.issues, [k]: next } };
}

const ART_LINE_RE = /^oc_artifacts:[^\n]*$/m;

function applyIssueComment(s: PmState, p: Json, botLogin: string, pmLogins: string[] = []): PmState {
  const c = p.comment;
  const i = p.issue;
  if (!c || !i || p.action !== "created" || "pull_request" in i) return s;
  const k = String(i.number);
  const isBot = c.user?.login === botLogin;
  let next: PmState = s;
  if (pmLogins.includes(c.user?.login) && /^\/oc\b/m.test(c.body ?? "")) {
    const prevL = s.launchedAt[k];
    if (!prevL || Date.parse(c.created_at) >= Date.parse(prevL)) {
      next = { ...next, launchedAt: { ...next.launchedAt, [k]: c.created_at } };
    }
  }
  if (pmLogins.includes(c.user?.login)) {
    const m = ART_LINE_RE.exec(c.body ?? "");
    const prev = s.pmArt[k];
    if (m && (!prev || Date.parse(c.created_at) >= Date.parse(prev.at))) {
      next = { ...next, pmArt: { ...next.pmArt, [k]: { at: c.created_at, line: m[0] } } };
    }
  }
  if (isBot) {
    const prev = s.botLast[k];
    if (!prev || Date.parse(c.created_at) >= Date.parse(prev.at)) {
      next = { ...next, botLast: { ...next.botLast, [k]: { issueNumber: i.number, at: c.created_at, body: (c.body ?? "").slice(0, 20000) } } };
    }
  }
  return next;
}

// issue_dependencies: blocked_by の追加・削除。blocked 側の issue 番号と blocker 番号だけを使う。
function applyDependencies(s: PmState, p: Json): PmState {
  const blocked = p.blocked_issue?.number;
  const blocker = p.blocking_issue?.number;
  if (!Number.isInteger(blocked) || !Number.isInteger(blocker)) return s;
  if (p.action !== "blocked_by_added" && p.action !== "blocked_by_removed" && p.action !== "blocking_added" && p.action !== "blocking_removed") return s;
  const k = String(blocked);
  const cur = s.blockedBy[k] ?? [];
  const adding = p.action === "blocked_by_added" || p.action === "blocking_added";
  const has = cur.includes(blocker);
  if (adding === has) return s;
  const known = k in s.blockedBy || !adding;
  const nextList = adding ? [...cur, blocker].sort((a: number, b: number) => a - b) : cur.filter((x) => x !== blocker);
  const summary = p.blocked_issue?.issue_dependencies_summary?.total_blocked_by;
  const blockedBy = { ...s.blockedBy, [k]: nextList };
  // 件数が合わない (一覧を取りこぼしている) 間は『不明』にして、reconcile が REST で取り直す。
  if (Number.isInteger(summary) && summary !== nextList.length) delete blockedBy[k];
  const cur0 = s.issues[k];
  const issues =
    cur0 && Number.isInteger(summary) ? { ...s.issues, [k]: { ...cur0, blockedByCount: summary } } : s.issues;
  return { ...s, blockedBy, issues };
}

function applyPr(s: PmState, p: Json): PmState {
  const pr = p.pull_request;
  if (!pr) return s;
  const k = String(pr.number);
  if (!newer(s.prs[k], pr.updated_at)) return s;
  const next: PrState = {
    number: pr.number,
    state: pr.state === "closed" ? "closed" : "open",
    merged: !!pr.merged_at,
    draft: !!pr.draft,
    ref: pr.head?.ref ?? "",
    title: pr.title ?? "",
    body: pr.state === "closed" ? "" : (pr.body ?? "").slice(0, 3000),
    updatedAt: pr.updated_at,
  };
  return { ...s, prs: { ...s.prs, [k]: next } };
}

function applyReview(s: PmState, p: Json): PmState {
  // レビューは PR の状態を変えない。PR の更新時刻だけ見て、無ければ何もしない。
  return p.pull_request ? applyPr(s, { pull_request: p.pull_request }) : s;
}

function applyRun(s: PmState, p: Json): PmState {
  const w = p.workflow_run;
  if (!w) return s;
  const k = String(w.id);
  if (!newer(s.runs[k], w.updated_at)) return s;
  const next: RunState = {
    id: w.id,
    event: w.event,
    title: w.display_title ?? w.name ?? "",
    status: w.status ?? "",
    conclusion: w.conclusion ?? null,
    updatedAt: w.updated_at,
  };
  return { ...s, runs: { ...s.runs, [k]: next } };
}

export function applyEvent(s: PmState, event: WebhookEvent, payload: Json, botLogin: string, pmLogins?: string[]): PmState {
  switch (event) {
    case "issues":
      return applyIssue(s, payload);
    case "issue_comment":
      return applyIssueComment(s, payload, botLogin, pmLogins);
    case "issue_dependencies":
      return applyDependencies(s, payload);
    case "pull_request":
      return applyPr(s, payload);
    case "pull_request_review":
      return applyReview(s, payload);
    case "workflow_run":
      return applyRun(s, payload);
  }
}

// POST /webhook の本体。順序は (1) 署名検証 (2) イベント種別 (3) JSON 解析 (4) 反映。
// (1) で失敗したら state は入力のまま返す (検証前に状態を変えない)。
export function handleWebhook(s: PmState, input: WebhookInput): WebhookResult {
  if (!verifySignature(input.secret, input.body, input.signature)) {
    return { status: 401, state: s, reason: "bad signature" };
  }
  if (!isEvent(input.event)) return { status: 202, state: s, reason: "ignored" };
  let payload: Json;
  try {
    payload = JSON.parse(input.body);
  } catch {
    return { status: 202, state: s, reason: "ignored" };
  }
  if (input.repo && payload?.repository?.full_name !== input.repo) return { status: 202, state: s, reason: "ignored" };
  return { status: 202, state: applyEvent(s, input.event, payload, input.botLogin, input.pmLogins), reason: "applied" };
}
