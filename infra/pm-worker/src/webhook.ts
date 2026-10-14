// webhook 受信の純関数。署名を検証してから状態を変える (未検証の入力では状態を一切変えない)。
// 永続化 (Durable Object / SQLite) は呼び出し側の責務。ここは state を受け取り、次の state を返すだけ。
import { verifySignature } from "./hmac.ts";

export const WEBHOOK_EVENTS = ["issues", "issue_comment", "pull_request", "pull_request_review", "workflow_run"] as const;
export type WebhookEvent = (typeof WEBHOOK_EVENTS)[number];

export interface IssueState {
  number: number;
  title: string;
  labels: string[];
  body: string;
  state: "open" | "closed";
  updatedAt: string;
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
}

export const EMPTY_STATE: PmState = { issues: {}, prs: {}, runs: {}, botLast: {} };

export interface WebhookInput {
  secret: string;
  event: string | null;
  signature: string | null | undefined;
  body: string;
  botLogin: string;
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
  const next: IssueState = {
    number: i.number,
    title: i.title,
    labels: (i.labels ?? []).map((l: Json) => l.name),
    body: i.body ?? "",
    state: i.state === "closed" ? "closed" : "open",
    updatedAt: i.updated_at,
  };
  return { ...s, issues: { ...s.issues, [k]: next } };
}

function applyIssueComment(s: PmState, p: Json, botLogin: string): PmState {
  const c = p.comment;
  const i = p.issue;
  if (!c || !i) return s;
  const k = String(i.number);
  const isBot = c.user?.login === botLogin;
  let next: PmState = s;
  if (isBot) {
    const prev = s.botLast[k];
    if (!prev || Date.parse(c.created_at) >= Date.parse(prev.at)) {
      next = { ...next, botLast: { ...next.botLast, [k]: { issueNumber: i.number, at: c.created_at, body: c.body ?? "" } } };
    }
  }
  return next;
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
    body: (pr.body ?? "").slice(0, 3000),
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

export function applyEvent(s: PmState, event: WebhookEvent, payload: Json, botLogin: string): PmState {
  switch (event) {
    case "issues":
      return applyIssue(s, payload);
    case "issue_comment":
      return applyIssueComment(s, payload, botLogin);
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
  return { status: 202, state: applyEvent(s, input.event, payload, input.botLogin), reason: "applied" };
}
