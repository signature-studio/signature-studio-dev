// webhook 受信の純関数。署名を検証してから状態を変える (未検証の入力では状態を一切変えない)。
// 永続化 (Durable Object / SQLite) は呼び出し側の責務。ここは state を受け取り、次の state を返すだけ。
import { verifySignature } from "./hmac.ts";
import { bodyArtLine } from "./launch.ts";
import { needsPmDecision } from "./needs.ts";
import { rateMarkRun } from "./ratealert.ts";
import { closeRefs, mentionRefs, refsOnlyNumbers } from "./refs.ts";

export const DEFAULT_REVIEWER_LOGIN = "oc-reviewer-for-signature-studio[bot]";
// 停止印 (oc-fix-limit) の作者。fix-progress.sh が job の GITHUB_TOKEN で投稿する (#2622・#2639)。実装 App 名義の印は agent が偽造できる。
export const DEFAULT_MARK_LOGIN = "github-actions[bot]";
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
  // 本文の最終の oc_artifacts 行 (検証済みの 1 行。先頭 4,000 字から抽出し、無ければ未設定)。launch の素材行の既定 (#2758)。本文が変わるたびに取り直す。
  artLine?: string;
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
  // merge の時刻と、本文が Refs #N のみ (Closes/Fixes なし) か。merge 済みの PR だけが持つ (本文そのものは持たない)。
  mergedAt?: string;
  refsOnly?: boolean;
  // merge 済み (closed) の PR の本文から読んだ Refs #N の番号 (閉じキーワードが無いときだけ。oc-pm の refs_orphan)。番号だけで、本文は持たない。
  refsOnlyNums?: number[];
}
// issue / PR ごとの終端状態の手がかり (oc-pm の検出に使う)。値は時刻・列挙値・真偽だけで、本文は持たない。
export interface Signal {
  // 最新の停止コメント (<!-- oc-fix-limit -->。作者は型 Bot かつ markLogin だけ)。intent は同じコメントの oc-pm-intent: stuck の reason (無ければ null)
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
  // 実装 run (issue_comment) が PR も出さずに打ち切られた (cancelled / failure / timed_out) 連続回数。KILLED_STOP_AT 回で自動の再着手を止める。
  // at はその run の完了時刻。PR・close・PM/人のコメント・成功した run で消す。
  kill?: { count: number; at: string };
  // 最後に数えた run の id。kill とは別に持ち、連続を消しても残す (完了済みの run の配送が再送・順不同で届いても、同じ run を数え直さない)。
  killRun?: number;
  // 最新の oc-pm-intent: relaunch (issue コメント)。書き手が実装 App かどうか (bot) と、マーカーの字句 (issue・arts・focus) だけを持つ。検査は engine が行う。
  relaunch?: { at: string; id?: number; bot: boolean; issue: string; arts: string; focus: string | null };
}

// 打ち切られた run を連続でこの回数数えた issue は、自動で再着手しない (oc:no-pr の reason=killed 相当)。PM agent (oc-pm の no_pr) の判断に回す。
export const KILLED_STOP_AT = 2;
const KILL_CONCLUSIONS = ["cancelled", "failure", "timed_out"];
// record-run-outcome.sh の『明示的な終了状態』(oc:stuck / needs-user-input / blocked) に、Worker の pm-apply (#2423 で user に置く issue) を足したもの。打ち切りを数えない。
const EXPLICIT_LABELS = ["oc:stuck", "needs-user-input", "blocked", "pm-apply"];
export interface RunState {
  id: number;
  event: string;
  title: string;
  status: string;
  conclusion: string | null;
  updatedAt: string;
  // run の作成時刻 (launch の観測に使う)。古い state には無い。
  createdAt?: string;
  // run を起こした workflow のファイル名 (`.github/workflows/opencode.yaml` なら `opencode.yaml`)。古い state には無い。
  wf?: string;
}

// 同時実行の上限 (60) を食う opencode.yaml の run だけを TARGET に数える。他の workflow (scripts-test.yaml など) は別枠。
export const OPENCODE_WORKFLOW = "opencode.yaml";

// workflow_run.path (REST は `.github/workflows/x.yaml`、ref 付きの形 `...@refs/heads/main` もあり得る) からファイル名を取る。
export function workflowFile(path: unknown): string | undefined {
  if (typeof path !== "string" || path === "") return undefined;
  const file = path.split("@")[0].split("/").pop() ?? "";
  return file === "" ? undefined : file;
}

// path を持たない run (古い保存値、path の無い配送) は opencode.yaml として数える。数え漏らして上限を超えるより、過大に数えるほうを選ぶ。
export const isOpencodeRun = (r: RunState): boolean => r.wf === undefined || r.wf === OPENCODE_WORKFLOW;
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
  // issue ごとの最後の bot の報告 (run-outcome・PM のマーカーを含むコメントを除く)。停止報告の素材名 (neededArts) の入力。botLast は run-outcome で上書きされるため別に持つ。
  botReport: Record<string, BotComment>;
  // PM のコメントに書かれた最後の `oc_artifacts:` 行 (分類の pm_art に相当)
  pmArt: Record<string, { at: string; line: string; id?: number }>;
  // issue dependencies (blocked_by) の blocker 番号 (open/closed 問わず。分類側で open だけに絞る)
  blockedBy: Record<string, number[]>;
  // PM (人間の PAT / PM App) が `/oc` コメントで着手を依頼した最後の時刻 (分類の launched に相当)
  launchedAt: Record<string, string>;
  // issue / PR 番号ごとの終端状態の手がかり
  sig: Record<string, Signal>;
  // 率制限のマーカー (cause=rate_limit) を付けた run の id ごとの記録 (bot の投稿)。後続のコメントで上書きされない。判定は engine の rateAlert。
  rateRuns: Record<string, { at: string; issue: number }>;
}

export const EMPTY_STATE: PmState = { issues: {}, prs: {}, runs: {}, botLast: {}, botReport: {}, pmArt: {}, blockedBy: {}, launchedAt: {}, sig: {}, rateRuns: {} };

export interface WebhookInput {
  secret: string;
  event: string | null;
  signature: string | null | undefined;
  body: string;
  botLogin: string;
  // 停止印 (oc-fix-limit) の作者。型 Bot でこの login の投稿だけを信じる。省略時は DEFAULT_MARK_LOGIN。
  markLogin?: string;
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
// 人として信じる author_association (起票者・コメント者の絞り込み。pm.ts の authorAllowed と userAt の両方で使う)。
export const ASSOC_OK = ["MEMBER", "OWNER", "COLLABORATOR"];

function applyIssue(s: PmState, p: Json): PmState {
  const i = p.issue;
  if (!i || "pull_request" in i) return s;
  const k = String(i.number);
  if (!newer(s.issues[k], i.updated_at)) return s;
  const closed = i.state === "closed";
  const art = closed ? null : bodyArtLine(i.body ?? "");
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
    ...(art ? { artLine: art } : {}),
  };
  let out: PmState = { ...s, issues: { ...s.issues, [k]: next } };
  // needs-user-input が付いた時刻。labeled の配送だけが時刻を持つ (REST は engine が events から補う)。外れたら消す。
  if (closed) out = setSig(out, k, { kill: undefined });
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

// run-outcome (実装 run の終了記録) と PM のマーカーを含むコメントは、停止報告ではない (tools/pm/issue_snapshot.py の bot_last_of と同じ)。
const NON_REPORT_MARKS = ["<!-- oc-run-outcome:", "<!-- oc-pm-"];
const isReportBody = (body: string): boolean => !NON_REPORT_MARKS.some((m) => body.includes(m));

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
  // 再投入の意図は bot の投稿でも botLast (停止報告の窓) を動かさない。意図の直後に窓が立つと、分類が 1.5 時間 recent になるため。
  if (isBot && !RELAUNCH_RE.test(c.body ?? "")) {
    const prev = s.botLast[k];
    if (!prev || notOlder(prev, c)) {
      next = { ...next, botLast: { ...next.botLast, [k]: { issueNumber: i.number, at: c.created_at, body: (c.body ?? "").slice(0, 20000), ...id } } };
    }
    const prevR = s.botReport[k];
    if (isReportBody(c.body ?? "") && (!prevR || notOlder(prevR, c))) {
      next = { ...next, botReport: { ...next.botReport, [k]: { issueNumber: i.number, at: c.created_at, body: (c.body ?? "").slice(0, 20000), ...id } } };
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

// oc-pm-intent: relaunch の属性を字句のまま取り出す (検証は engine の checkRelaunchIntent)。マーカーが無ければ null。
const RELAUNCH_RE = /<!-- oc-pm-intent: relaunch ([^>]{0,300})-->/;
export function parseRelaunchIntent(body: string): { issue: string; arts: string; focus: string | null } | null {
  const m = RELAUNCH_RE.exec(body);
  if (!m) return null;
  return {
    issue: /(?:^|\s)issue=(\S*)/.exec(m[1])?.[1] ?? "",
    arts: /(?:^|\s)arts="([^"]*)"/.exec(m[1])?.[1] ?? "",
    focus: /(?:^|\s)focus=(\S*)/.exec(m[1])?.[1] ?? null,
  };
}

// コメントから終端状態の手がかりを取る。マーカーは bot の投稿だけを信じる (誰でもコメントできるため)。停止印は markLogin の投稿だけ (#2639)。
function applySignalComment(s: PmState, p: Json, botLogin: string, pmLogins: string[], reviewer: string, mark: string): PmState {
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
  // 停止印は窓の印と同じ作者 (型 Bot・markLogin) の投稿だけ。実装 App・reviewer 名義の印は信じない (#2639)。
  const stopper = c.user?.type === "Bot" && login === mark;
  if (stopper && body.includes(STOP_MARK) && later(cur?.stop?.at)) patch.stop = { at, intent: parseStuckIntent(body, i.number) };
  if (trusted && later(cur?.outcome?.at)) {
    const reason = parseOutcomeReason(body);
    if (reason) patch.outcome = { at, reason };
  }
  if ((pmLogins.includes(login) || (trusted && PM_MARK_RE.test(body))) && later(cur?.pmAt)) patch.pmAt = at;
  // 再投入の意図は issue のコメントだけ。実装 App の意図は第三者の意図より優先する (第三者の後に来ても置き換えない)。
  // 同じ区分の中では最新を残す。どの順に適用しても結果は同じ。第三者の意図も残す (engine が author として拒否し、counters に記録する)。
  const rel = !("pull_request" in i) ? parseRelaunchIntent(body) : null;
  const impl = login === botLogin;
  if (rel && (!cur?.relaunch || (impl && !cur.relaunch.bot) || (impl === cur.relaunch.bot && notOlder(cur.relaunch, c)))) {
    patch.relaunch = { at, ...(typeof c.id === "number" ? { id: c.id } : {}), bot: impl, ...rel };
  }
  // 人の回答は、非 bot かつ MEMBER / OWNER / COLLABORATOR のコメントだけ (第三者のコメントで PM を起こさない)。
  const human = !!login && !isBotUser(c.user) && ASSOC_OK.includes(c.author_association);
  if (human && later(cur?.userAt)) patch.userAt = at;
  // 打ち切りの連続は、その後の PM の応答 (PM のログインか PM のマーカー付き bot コメント) か人の回答で解く。`/oc` の投稿は着手であって応答ではない
  // (Worker 自身の再投稿が解除にならないように。PM のログインは Worker の PM App を含む)。
  const answered = !/^\/oc\b/m.test(body) && (pmLogins.includes(login) || (trusted && PM_MARK_RE.test(body)) || human);
  if (answered && cur?.kill && Date.parse(at) > Date.parse(cur.kill.at)) patch.kill = undefined;
  return setSig(s, k, patch);
}

// 率制限のマーカー (cause=rate_limit run=N) を、bot (実装・reviewer の App) の投稿から run id ごとに残す。issue でも PR でも数える。
// botLast と違って後続のコメントで上書きされない。同じ run の 2 件目は残さない (先に来たものを残す)。
function applyRateMarker(s: PmState, p: Json, botLogin: string, reviewer: string): PmState {
  const c = p.comment;
  const i = p.issue;
  if (!c || !i || p.action !== "created" || typeof c.created_at !== "string") return s;
  if (c.user?.login !== botLogin && c.user?.login !== reviewer) return s;
  const run = rateMarkRun(c.body ?? "");
  if (run === undefined || s.rateRuns[String(run)]) return s;
  return { ...s, rateRuns: { ...s.rateRuns, [String(run)]: { at: c.created_at, issue: i.number } } };
}

function applyIssueComment(s: PmState, p: Json, botLogin: string, pmLogins: string[] = [], reviewer: string = DEFAULT_REVIEWER_LOGIN, mark: string = DEFAULT_MARK_LOGIN): PmState {
  return applyRateMarker(applySignalComment(applyBotComment(s, p, botLogin, pmLogins), p, botLogin, pmLogins, reviewer, mark), p, botLogin, reviewer);
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

// 本文が『Refs #N のみ』か (issue を閉じない merge の判定)。Closes / Fixes / Resolves の語が 1 つでもあれば false。大文字小文字は区別しない。
const REFS_RE = /\bRefs:?\s+(?:[\w.-]+\/[\w.-]+)?#\d+/i;
const CLOSE_RE = /\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+(?:[\w.-]+\/[\w.-]+)?#\d+/i;
export function refsOnlyBody(body: string): boolean {
  return REFS_RE.test(body) && !CLOSE_RE.test(body);
}

function applyPr(s: PmState, p: Json): PmState {
  const pr = p.pull_request;
  if (!pr) return s;
  const k = String(pr.number);
  if (!newer(s.prs[k], pr.updated_at)) return s;
  const full = typeof pr.body === "string" ? pr.body : "";
  const merged = !!pr.merged_at;
  const next: PrState = {
    number: pr.number,
    state: pr.state === "closed" ? "closed" : "open",
    merged,
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
    // 切り詰める前の完全な本文から真偽だけを取る (本文は保存しない)。
    ...(merged ? { mergedAt: String(pr.merged_at), refsOnly: refsOnlyBody(pr.body ?? "") } : {}),
    // 本文は closed で捨てるので、merge 時点の本文から Refs の番号だけを残す (REST の一覧・webhook のどちらでも同じ)。
    ...(pr.state === "closed" && pr.merged_at ? { refsOnlyNums: refsOnlyNumbers(pr.body ?? "") } : {}),
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
  // path は run 自身 (REST・webhook とも) か、webhook の workflow オブジェクトにある。配送に無いときは既知の値を残す。
  const wf = workflowFile(w.path ?? p.workflow?.path) ?? s.runs[k]?.wf;
  const next: RunState = {
    id: w.id,
    event: w.event,
    title: w.display_title ?? w.name ?? "",
    status: w.status ?? "",
    conclusion: w.conclusion ?? null,
    updatedAt: w.updated_at,
    ...(typeof w.created_at === "string" ? { createdAt: w.created_at } : {}),
    ...(wf ? { wf } : {}),
  };
  return { ...s, runs: { ...s.runs, [k]: next } };
}

// issue n を指す open PR があるか (ブランチ名 <n>-... か本文の Closes / Refs / Fixes / Resolves #n。record-run-outcome.sh と同じ判定・同じ語の集合)。
const PR_MENTION_RE = /\b(?:closes|refs|fixes|resolves) #(\d+)/gi;
function prIssues(pr: { ref?: string; body?: string }): number[] {
  const out = new Set<number>();
  const m = /^(\d+)-/.exec(pr.ref ?? "");
  if (m) out.add(Number(m[1]));
  for (const x of (pr.body ?? "").matchAll(PR_MENTION_RE)) out.add(Number(x[1]));
  return [...out];
}
export function hasOpenPr(s: PmState, n: number): boolean {
  return Object.values(s.prs).some((p) => p.state === "open" && prIssues(p).includes(n));
}
// open な PR に加えて、since 以降に merge された PR も着手の証拠にする (run 中に open から merge まで済んだ PR は open の一覧に出ない。record-run-outcome.sh と同じ)。
// closed の PR は本文を持たない (applyPr) ので、merge 済みの PR はブランチ名 N-... だけで当てる。
function hasPrSince(s: PmState, n: number, since: string | undefined): boolean {
  const t = Date.parse(since ?? "");
  return Object.values(s.prs).some(
    (p) => prIssues(p).includes(n) && (p.state === "open" || (p.merged && Number.isFinite(t) && Date.parse(p.mergedAt ?? "") >= t)),
  );
}

// PR が出たら、その issue の打ち切りの連続を消す (着手済みになった)。
function clearKillByPr(s: PmState, pr: Json | undefined): PmState {
  if (!pr || pr.state !== "open") return s;
  let out = s;
  for (const n of prIssues({ ref: pr.head?.ref, body: pr.body })) out = s.sig[String(n)]?.kill ? setSig(out, String(n), { kill: undefined }) : out;
  return out;
}

// 完了した実装 run (issue_comment) が PR も出さずに打ち切られた回数を、issue ごとに数える (record-run-outcome.sh の always() step は
// runner の shutdown で走らないので、oc:no-pr は付かない。conclusion は workflow_run の配送で分かる)。
//  - 数える: conclusion が cancelled / failure / timed_out。題名が一意な open issue に当たり、PR (open か run の開始以降に merge) も明示的な終了状態も無い。
//  - 数えない: 後続の run がある (concurrency で置換された待機中の run。コメントで起きて skipped になった run は後続に数えない)。
//  - 成功した run は連続を断つ。skipped などの run は断たない (agent 自身のコメントでも issue_comment の run が起きる)。
// 同じ run の再配送と順不同の配送は、最後に数えた run の id (killRun。連続の解除では消さない) より大きい run だけを数えて重ねない。
function applyKill(prev: PmState, next: PmState, w: Json | undefined): PmState {
  if (next === prev || !w) return next;
  const run = next.runs[String(w.id)];
  if (!run || run.event !== "issue_comment" || run.status !== "completed") return next;
  // conclusion が分かっている完了済みの run の再配送は数えない (reconcile が『一覧に無い』ことから付ける conclusion=unknown は、本当の完了の配送で上書きする)
  const was = prev.runs[String(w.id)];
  if (was?.status === "completed" && was.conclusion !== "unknown") return next;
  const conclusion = run.conclusion ?? "";
  if (conclusion !== "success" && !KILL_CONCLUSIONS.includes(conclusion)) return next;
  const title = run.title.trim();
  const hits = Object.values(next.issues).filter((i) => i.state === "open" && i.title.trim() === title);
  if (hits.length !== 1) return next;
  const issue = hits[0];
  const k = String(issue.number);
  const cur = next.sig[k]?.kill;
  const counted = next.sig[k]?.killRun;
  if (counted !== undefined && run.id <= counted) return next;
  if (conclusion === "success") return cur ? setSig(next, k, { kill: undefined }) : next;
  if (Object.values(next.runs).some((r) => r.id > run.id && r.event === "issue_comment" && r.title.trim() === title && !(r.status === "completed" && r.conclusion === "skipped"))) return next;
  if (issue.labels.some((l) => EXPLICIT_LABELS.includes(l)) || issue.blockedByCount > 0) return next;
  if (hasPrSince(next, issue.number, run.createdAt)) return cur ? setSig(next, k, { kill: undefined }) : next;
  return setSig(next, k, { kill: { count: (cur?.count ?? 0) + 1, at: run.updatedAt }, killRun: run.id });
}

export function applyEvent(
  s: PmState,
  event: WebhookEvent,
  payload: Json,
  botLogin: string,
  pmLogins?: string[],
  reviewerLogin: string = DEFAULT_REVIEWER_LOGIN,
  markLogin: string = DEFAULT_MARK_LOGIN,
): PmState {
  switch (event) {
    case "issues":
      return applyIssue(s, payload);
    case "issue_comment":
      return applyIssueComment(s, payload, botLogin, pmLogins, reviewerLogin, markLogin);
    case "issue_dependencies":
      return applyDependencies(s, payload);
    case "pull_request":
      return clearKillByPr(applyPr(s, payload), payload.pull_request);
    case "pull_request_review":
      return clearKillByPr(applyReview(s, payload, reviewerLogin), payload.pull_request);
    case "workflow_run":
      return applyKill(s, applyRun(s, payload), payload.workflow_run);
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
  return { status: 202, state: applyEvent(s, input.event, payload, input.botLogin, input.pmLogins, input.reviewerLogin, input.markLogin), reason: "applied" };
}
