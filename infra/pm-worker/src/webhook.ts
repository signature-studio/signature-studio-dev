// webhook 受信の純関数。署名を検証してから状態を変える (未検証の入力では状態を一切変えない)。
// 永続化 (Durable Object / SQLite) は呼び出し側の責務。ここは state を受け取り、次の state を返すだけ。
import { verifySignature } from "./hmac.ts";
import { needsPmDecision } from "./needs.ts";
import { closeRefs, mentionRefs } from "./refs.ts";

export const DEFAULT_REVIEWER_LOGIN = "oc-reviewer-for-signature-studio[bot]";
export const NEEDS_USER_LABEL = "needs-user-input";

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
  // 起票者 (oc-pm の対象の絞り込みに使う。古い保存値には無いので参照側で未設定を『許可しない』と扱う)
  author?: string;
  authorType?: string;
  assoc?: string;
}
export interface PrState {
  number: number;
  state: "open" | "closed";
  merged: boolean;
  draft: boolean;
  ref: string;
  title: string;
  body: string;
  // ラベル名。oc:stuck の除外に使う (古い保存値には無いので参照側で ?? [] とする)
  labels: string[];
  updatedAt: string;
  author?: string;
  authorType?: string;
  assoc?: string;
  // 保存前の全文 (body は切るか closed で空にするため) から取った参照。古い保存値には無い (規則 A は無いものを参照しない)。
  // closes: Closes / Fixes / Resolves / Refs で参照する issue 番号 (規則 A の merged PR)。
  closes?: number[];
  // mentions: 題名と本文に現れる #番号。open PR が親 issue を参照しているかの判定 (規則 A の除外) に使う。
  mentions?: number[];
}
// issue / PR ごとの終端状態の手がかり (oc-pm の検出に使う)。値は時刻・列挙値・真偽だけで、本文は持たない。
export interface Signal {
  // 最新の停止コメント (<!-- oc-fix-limit -->、bot 投稿)。intent は同じコメントの oc-pm-intent: stuck の reason (無ければ null)
  stop?: { at: string; intent: string | null };
  // 最後の <!-- oc-run-outcome: no-pr ... --> (bot 投稿)
  outcome?: { at: string; reason: string };
  // reviewer の最新の verdict (APPROVED / CHANGES_REQUESTED)。needs は差し戻し本文が NEEDS_KEY に一致したか
  review?: { at: string; state: "APPROVED" | "CHANGES_REQUESTED"; needs: boolean };
  // PM の応答 (PM のログイン、または PM agent のマーカー付き bot コメント) の最新時刻
  pmAt?: string;
  // 非 bot ユーザーの最新コメント時刻
  userAt?: string;
  // ラベル needs-user-input が付いた時刻
  labelAt?: string;
  // reviews を REST で一度取得した
  revChecked?: boolean;
}
export interface RunState {
  id: number;
  event: string;
  title: string;
  status: string;
  conclusion: string | null;
  updatedAt: string;
  // run の作成時刻 (launch の観測に使う)。古い state には無い。
  createdAt?: string;
}
export interface BotComment {
  issueNumber: number;
  at: string;
  body: string;
  // コメントの id。created_at が同時刻 (秒精度) のコメントの新旧を、適用順に依らず決めるために持つ。
  id?: number;
}
export interface PmState {
  issues: Record<string, IssueState>;
  prs: Record<string, PrState>;
  runs: Record<string, RunState>;
  // issue ごとの最後の bot コメント (分類の bot_last に相当)
  botLast: Record<string, BotComment>;
  // PM のコメントに書かれた最後の `oc_artifacts:` 行 (分類の pm_art に相当)
  pmArt: Record<string, { at: string; line: string; id?: number }>;
  // issue dependencies (blocked_by) の blocker 番号 (open/closed 問わず。分類側で open だけに絞る)
  blockedBy: Record<string, number[]>;
  // PM (人間の PAT / PM App) が `/oc` コメントで着手を依頼した最後の時刻 (分類の launched に相当)
  launchedAt: Record<string, string>;
  // issue / PR 番号ごとの終端状態の手がかり
  sig: Record<string, Signal>;
}

export const EMPTY_STATE: PmState = { issues: {}, prs: {}, runs: {}, botLast: {}, pmArt: {}, blockedBy: {}, launchedAt: {}, sig: {} };

export interface WebhookInput {
  secret: string;
  event: string | null;
  signature: string | null | undefined;
  body: string;
  botLogin: string;
  // PM のログイン名 (人間の PAT と PM App の bot)。`oc_artifacts:` 行の取得に使う。省略時は取得しない。
  pmLogins?: string[];
  // reviewer の bot ログイン。review の verdict とマーカー付きコメントの信頼に使う。省略時は既定。
  reviewerLogin?: string;
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

const sameJson = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b);

// sig[k] に patch を反映する。undefined の値はキーを消す。変わらなければ s をそのまま返す (永続化の差分を出さない)。
export function setSig(s: PmState, k: string, patch: Partial<Signal>): PmState {
  const cur = s.sig[k];
  const next: Record<string, unknown> = { ...(cur ?? {}) };
  let changed = false;
  for (const [key, v] of Object.entries(patch)) {
    if (v === undefined) {
      if (key in next) {
        delete next[key];
        changed = true;
      }
    } else if (!sameJson(next[key], v)) {
      next[key] = v;
      changed = true;
    }
  }
  if (!changed) return s;
  return { ...s, sig: { ...s.sig, [k]: next as Signal } };
}

export const isBotUser = (u: Json | undefined | null): boolean => u?.type === "Bot" || /\[bot\]$/.test(u?.login ?? "");

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
    author: i.user?.login ?? s.issues[k]?.author,
    authorType: i.user?.type ?? s.issues[k]?.authorType,
    assoc: i.author_association ?? s.issues[k]?.assoc,
  };
  let out: PmState = { ...s, issues: { ...s.issues, [k]: next } };
  // needs-user-input が付いた時刻。labeled の配送だけが時刻を持つ (REST は engine が events から補う)。外れたら消す。
  if (closed || !next.labels.includes(NEEDS_USER_LABEL)) out = setSig(out, k, { labelAt: undefined });
  else if (p.action === "labeled" && p.label?.name === NEEDS_USER_LABEL) out = setSig(out, k, { labelAt: i.updated_at });
  return out;
}

const ART_LINE_RE = /^oc_artifacts:[^\n]*$/m;

// c が prev と同じか新しいコメントなら true。created_at が同時刻なら id の大きい方を新しいとみなす
// (id が無ければ同時刻は後から適用した方が勝つ)。どの順に適用しても、最新のコメントが残る。
function notOlder(prev: { at: string; id?: number }, c: Json): boolean {
  const a = Date.parse(c.created_at);
  const b = Date.parse(prev.at);
  if (a !== b) return a > b;
  return typeof c.id === "number" && typeof prev.id === "number" ? c.id >= prev.id : true;
}

function applyBotComment(s: PmState, p: Json, botLogin: string, pmLogins: string[] = []): PmState {
  const c = p.comment;
  const i = p.issue;
  if (!c || !i || p.action !== "created" || "pull_request" in i) return s;
  const k = String(i.number);
  const isBot = c.user?.login === botLogin;
  const id = typeof c.id === "number" ? { id: c.id } : {};
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
    if (m && (!prev || notOlder(prev, c))) {
      next = { ...next, pmArt: { ...next.pmArt, [k]: { at: c.created_at, line: m[0], ...id } } };
    }
  }
  if (isBot) {
    const prev = s.botLast[k];
    if (!prev || notOlder(prev, c)) {
      next = { ...next, botLast: { ...next.botLast, [k]: { issueNumber: i.number, at: c.created_at, body: (c.body ?? "").slice(0, 20000), ...id } } };
    }
  }
  return next;
}

const STOP_MARK = "<!-- oc-fix-limit -->";
const INTENT_RE = /<!-- oc-pm-intent: stuck pr=(\d{1,7})(?: reason=([a-z-]{1,20}))?[^>]*-->/;
const OUTCOME_RE = /<!-- oc-run-outcome: no-pr reason=([a-z]{1,20})(?:[^>]*)-->/;
const PM_MARK_RE = /<!-- oc-pm-(?:decision:|intent: relaunch)/;
export const OUTCOME_REASONS = ["stop", "split", "blocked", "artifact", "unknown"];
export const STUCK_REASONS = ["repeat", "ceiling", "code", "pm-decision", "user-decision", "unknown"];

// 停止コメントの oc-pm-intent: stuck。pr= が当該 PR の番号と合わなければ無効 (コピーされた古いマーカーを拾わない)。
// reason は列挙外なら unknown (fix-progress.sh の reset など、値域外でも『stuck の意図』自体は有効とする)。
export function parseStuckIntent(body: string, pr: number): string | null {
  const m = INTENT_RE.exec(body);
  if (!m || Number(m[1]) !== pr) return null;
  return m[2] && STUCK_REASONS.includes(m[2]) ? m[2] : "unknown";
}

export function parseOutcomeReason(body: string): string | null {
  const m = OUTCOME_RE.exec(body);
  if (!m) return null;
  return OUTCOME_REASONS.includes(m[1]) ? m[1] : "unknown";
}

// コメントから終端状態の手がかりを取る。マーカーは bot (実装 App・reviewer App) の投稿だけを信じる (誰でもコメントできるため)。
function applySignalComment(s: PmState, p: Json, botLogin: string, pmLogins: string[], reviewer: string): PmState {
  const c = p.comment;
  const i = p.issue;
  if (!c || !i || p.action !== "created" || !Number.isInteger(i.number)) return s;
  const at: unknown = c.created_at;
  if (typeof at !== "string" || Number.isNaN(Date.parse(at))) return s;
  const k = String(i.number);
  const login: string = c.user?.login ?? "";
  const body: string = c.body ?? "";
  const cur = s.sig[k];
  const later = (prev: string | undefined): boolean => !prev || Date.parse(at) >= Date.parse(prev);
  const trusted = isBotUser(c.user) && (login === botLogin || login === reviewer);
  const patch: Partial<Signal> = {};
  if (trusted && body.includes(STOP_MARK) && later(cur?.stop?.at)) patch.stop = { at, intent: parseStuckIntent(body, i.number) };
  if (trusted && later(cur?.outcome?.at)) {
    const reason = parseOutcomeReason(body);
    if (reason) patch.outcome = { at, reason };
  }
  if ((pmLogins.includes(login) || (trusted && PM_MARK_RE.test(body))) && later(cur?.pmAt)) patch.pmAt = at;
  if (login && !isBotUser(c.user) && later(cur?.userAt)) patch.userAt = at;
  return setSig(s, k, patch);
}

function applyIssueComment(s: PmState, p: Json, botLogin: string, pmLogins: string[] = [], reviewer: string = DEFAULT_REVIEWER_LOGIN): PmState {
  return applySignalComment(applyBotComment(s, p, botLogin, pmLogins), p, botLogin, pmLogins, reviewer);
}

// reviewer の verdict (APPROVED / CHANGES_REQUESTED) を PR の手がかりに反映する。COMMENTED は verdict ではない。
export function reviewSignal(s: PmState, pr: number, r: Json, reviewer: string): PmState {
  if (!r || r.user?.login !== reviewer) return s;
  const state = String(r.state ?? "").toUpperCase();
  const at: unknown = r.submitted_at;
  if ((state !== "APPROVED" && state !== "CHANGES_REQUESTED") || typeof at !== "string" || Number.isNaN(Date.parse(at))) return s;
  const prev = s.sig[String(pr)]?.review;
  if (prev && Date.parse(at) < Date.parse(prev.at)) return s;
  return setSig(s, String(pr), { review: { at, state, needs: state === "CHANGES_REQUESTED" && needsPmDecision(r.body) } });
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
  const full = typeof pr.body === "string" ? pr.body : "";
  const next: PrState = {
    number: pr.number,
    state: pr.state === "closed" ? "closed" : "open",
    merged: !!pr.merged_at,
    draft: !!pr.draft,
    ref: pr.head?.ref ?? "",
    title: pr.title ?? "",
    body: pr.state === "closed" ? "" : full.slice(0, 3000),
    labels: Array.isArray(pr.labels) ? pr.labels.map((l: any) => String(l?.name ?? "")) : [],
    updatedAt: pr.updated_at,
    author: pr.user?.login ?? s.prs[k]?.author,
    authorType: pr.user?.type ?? s.prs[k]?.authorType,
    assoc: pr.author_association ?? s.prs[k]?.assoc,
    closes: closeRefs(full),
    mentions: mentionRefs(`${pr.title ?? ""}\n${full}`),
  };
  return { ...s, prs: { ...s.prs, [k]: next } };
}

function applyReview(s: PmState, p: Json, reviewer: string): PmState {
  // レビューは PR の状態を変えない (PR の更新時刻だけ見る)。reviewer の verdict は手がかりとして残す。
  let next = p.pull_request ? applyPr(s, { pull_request: p.pull_request }) : s;
  const n = p.pull_request?.number;
  if (!p.review || !Number.isInteger(n)) return next;
  if (p.action === "submitted") next = reviewSignal(next, n, p.review, reviewer);
  else if (p.action === "dismissed" && next.sig[String(n)]?.review?.at === p.review.submitted_at) {
    // 取り消された verdict は捨てて、REST で取り直させる
    next = setSig(next, String(n), { review: undefined, revChecked: undefined });
  }
  return next;
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
    ...(typeof w.created_at === "string" ? { createdAt: w.created_at } : {}),
  };
  return { ...s, runs: { ...s.runs, [k]: next } };
}

export function applyEvent(
  s: PmState,
  event: WebhookEvent,
  payload: Json,
  botLogin: string,
  pmLogins?: string[],
  reviewerLogin: string = DEFAULT_REVIEWER_LOGIN,
): PmState {
  switch (event) {
    case "issues":
      return applyIssue(s, payload);
    case "issue_comment":
      return applyIssueComment(s, payload, botLogin, pmLogins, reviewerLogin);
    case "issue_dependencies":
      return applyDependencies(s, payload);
    case "pull_request":
      return applyPr(s, payload);
    case "pull_request_review":
      return applyReview(s, payload, reviewerLogin);
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
  return { status: 202, state: applyEvent(s, input.event, payload, input.botLogin, input.pmLogins, input.reviewerLogin), reason: "applied" };
}
