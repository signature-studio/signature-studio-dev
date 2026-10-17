// PM の本体: 状態の同期 (full / reconcile)・分類・launch の選定と実行・watchdog dispatch・status。
// 時刻・fetch・保管先は注入する (テストでは MemoryStore と fetch モック)。dry-run が既定で、GitHub への書き込みは経路ごとのスイッチが "1" のときだけ:
//   launch (/oc コメント) = LIVE_LAUNCH、repository_dispatch (oc-watchdog と oc-pm) = LIVE_DISPATCH。どちらも未設定なら LIVE に従う。
import { AUTO_CLOSE_MAX, AUTO_CLOSE_RETRY_MS, AUTO_CLOSE_WOULD_MS, closeComment, detectRuleA, type CloseTarget } from "./autoclose.ts";
import { countOpencodeRuns, countRunsByPrio, type ActiveCount } from "./active.ts";
import { classify, isStopReport, neededArtsOf, RUN_WINDOW_H, type ClassifyInput, type Rows, type Snapshot } from "./classify.ts";
import type { Config } from "./config.ts";
import { Gh, GhError, type ListResult } from "./github.ts";
import { addArts, buildLaunchBody, checkRelaunchIntent, defaultArtLine, effectivePrioMap, lowAllowance, noPrCooldownMs, planLaunch, relaunchAuthorOf, RELAUNCH_WINDOW_MS, validateArtLine, type LowCap, type Prio } from "./launch.ts";
import { advanceLaunch, doneAtOf, observedBy, type LaunchObs, type LaunchState } from "./launchobs.ts";
import type { Store } from "./kvstore.ts";
import { haltNotifyDue, haltOverdue, haltReasons, nextHalt, type Halt } from "./halt.ts";
import { countOpenPrs, nextReviewOnly, type PhaseState } from "./phase.ts";
import {
  detectPm,
  DIGEST_EVERY_MS,
  DIGEST_KIND,
  DIGEST_REF,
  PM_LIMITS,
  pruneHistory,
  selectDispatch,
  selectWake,
  validPayload,
  DETECTED_KINDS,
  HOLD_LABELS,
  NEEDS_PM_LABEL,
  NO_PR_LABEL,
  STUCK_LABEL,
  type HistoryEntry,
  type PmTarget,
  type SkipEntry,
} from "./pm.ts";
import { RATE_EVAL_GAP_MS, RATE_EVAL_MAX_GAP_MS, RATE_STREAK, RATE_WINDOW_MS, rateHit } from "./ratealert.ts";
import { RATE_GUARD, restGuardOn, type RateInfo } from "./ratelimit.ts";
import { readyHold, recentHold, stoppedHold, type Hold } from "./holdinfo.ts";
import { redact } from "./redact.ts";
import { aePoint, metricsRow, type AeSink } from "./metrics.ts";
import type { VmState } from "./vmstate.ts";
import { appendSample, capValue, nextCap, peakRunning, targetEff, type Cap, type Sample } from "./saturation.ts";
import {
  applyEvent,
  EMPTY_STATE,
  isOpencodeRun,
  KILLED_STOP_AT,
  NEEDS_USER_LABEL,
  reviewSignal,
  setSig,
  type IssueState,
  type PmState,
  type PrState,
  type RunState,
  WEBHOOK_EVENTS,
  handleWebhook,
  prioIssues,
  type WebhookResult,
} from "./webhook.ts";

export const FULL_SYNC_EVERY_MS = 6 * 3_600_000;
// 全体同期が書く派生値の版 (2: issue の起票者 author/assoc と、PR・issue の手がかり sig.outcome など #2333)。
// 保存値の版が違う (未記録・導入より前に保存された状態) ときは、周期を待たずに全体同期を走らせて補完する。その失敗の再試行は SIGNAL_RETRY_MS ごと。
export const SIGNAL_VER = 2;
export const SIGNAL_RETRY_MS = 15 * 60_000;
// reconcile がこれ以上止まっていたら、状態が古いとみなして launch しない (誤った着手を避ける)。
export const STALE_AFTER_MS = 15 * 60_000;
const NO_PR_MAX_RELAUNCH = 3;
// 停止報告 (stopped) のうち、再投入の意図でも着手させないもの (未観測の launch)。他の stopped は PM の判断待ちなので、意図で扱ってよい。
// 親 (open な子を持つ issue) は理由の文字列ではなく子の有無で見る (intentGate)。
const INTENT_HARD_STOP = ["launch-unobserved"];
// oc-watchdog の最短送信間隔は WATCHDOG_INTERVAL_S (既定 300 秒 = VM の pm_watchdog_ping.sh と同じ 5 分) から、この分だけ短い。
// tick は毎分 (cron と alarm) で、わずかに早い tick を弾くと次の送信が 1 分遅れ、周期が 6 分になるため。
export const WATCHDOG_JITTER_MS = 30_000;
// 降格 (#2340): 同じ issue に、この時間内に Worker (PM App) と個人の /oc の組が付いたら DO を dry-run に戻す。
export const OC_DOUBLE_MS = 30 * 60_000;
// 降格の時限復帰 (CI-251)。降格からこの時間を超えたら tick が自動で解除する。
export const DEMOTE_AUTO_LIFT_MS = 60 * 60_000;
// shadow (#2340): would_launch と VM の /oc を、この窓 (15 分) で突き合わせる。
export const SHADOW_WINDOW_MS = 15 * 60_000;
const OC_KEEP_MS = 2 * 3_600_000;
const OC_RE = /^\/oc\b/m;

// PM のログイン (個人と PM App) が付けた /oc の記録。vm は PM の個人アカウント (VM の投稿の正)。
export interface OcPost {
  n: number;
  id: number;
  at: number;
  vm: boolean;
}
// dry-run 中の各 tick の would_launch (計画に載った issue 番号)。
export interface WouldRec {
  at: number;
  ns: number[];
}

// 管理用の全体同期 (POST /admin/resync) は 1 時間に RESYNC_PER_HOUR 回まで (試行は失敗しても数える)。
export const RESYNC_PER_HOUR = 2;
// 失敗した配送の走査は REDELIVER_EVERY_MS ごと。1 走査の再配送は REDELIVER_MAX_PER_SCAN 件まで、同じ guid は REDELIVER_MAX_PER_GUID 回まで。
export const REDELIVER_EVERY_MS = 5 * 60_000;
export const REDELIVER_MAX_PER_SCAN = 10;
export const REDELIVER_MAX_PER_GUID = 3;
const HOUR_MS = 3_600_000;
// VM の状態を取り込む前の launch 停止 (#2343)。/status.launch_blocked と plan.blocked に出す。
export const NO_IMPORT = "no-import";
// open issue 数の履歴は 1 時間ごとに 1 点、最大 48 点 (48 時間分)。open_issues_delta_24h の基準に使う。
export const OPEN_SAMPLE_MS = 3_600_000;
export const OPEN_SAMPLE_MAX = 48;
const DAY_MS = 24 * 3_600_000;

export interface OpenSample {
  at: number;
  open: number;
}

export interface Planned {
  n: number;
  art: string;
  relaunch: boolean;
  // oc:no-pr の再投入の理由 (計数の対象。stop・split は再投入しない)
  np?: NoPrReason;
  // np が blocked のとき、再着手の根拠にした blocked の報告 (run-outcome) の時刻。同じ報告では 2 回目を出さない。
  reportAt?: string;
  // 新しい素材の無い artifact を unknown の枠で再投入したとき (#3185)。本文に『前回の停止の理由を再確認』の行を足す。
  recheck?: boolean;
}

type NoPrReason = "artifact" | "unknown" | "blocked";

// relaunch バケットの np:<n> (oc:no-pr の再投入の計数。count は artifact・unknown・blocked の再投入の合計)
interface NoPrCount {
  count: number;
  unknown: number;
  artifact: number;
  // 最後に blocked の再着手をした報告の時刻 (run-outcome の at)。報告ごとに 1 回だけ再着手する。
  blocked?: string;
  art: string | null;
}

export interface Plan {
  at: string;
  // opencode.yaml の未完了の run の総数 (実装・review・fix・oc-pm・watchdog)。room = max(0, target - active)。
  active: number;
  active_impl: number;
  active_other: number;
  // 設定の上限 (TARGET)。room は下の targetEff から計算する。
  target: number;
  // 観測から推定した同時実行の上限を足した目標 (TARGET を超えない)。推定が無ければ target と同じ。
  targetEff: number;
  capEst?: number;
  room: number;
  picks: Planned[];
  // Review-Only (指示 130)。true の間は picks を空にする。
  phase: PhaseState;
  open_prs_excl_stuck: number;
  stuck_prs: number;
  // launch を止める理由 (stuck-ceiling / rate-guard)。止めないなら undefined。
  stop?: string;
  // 新規・再投入の picks を空にしている理由 (no-import)。止めないなら undefined。
  blocked?: typeof NO_IMPORT;
  // 未完了の run を優先の区分別に数えた値 (active_all と合計が一致する。対応の取れない run は normal)。
  active_by_prio: Record<Prio, number>;
  // prio:low の上限 (LOW_CAP)。applied は prio:critical が着手済みか launch 可能な間だけ真。
  low_cap: LowCap;
  // 着手待ち (ready) で今回 launch されない issue と理由 (#5110)。観測のみ。gate (review-only・stuck-ceiling・rate-guard・no-import) で止めているときは全件がその理由。
  ready_held: { n: number; why: string }[];
}

interface Meta {
  fullSyncAt?: number;
  // 保存値の版 (SIGNAL_VER)。全体同期が完了したときに記録する。版の補完を最後に試した時刻 (再試行の間隔に使う)。
  signalVer?: number;
  signalTryAt?: number;
  reconcileAt?: number;
  watchdogAt?: number;
  tickAt?: number;
  // 署名を検証できた webhook の最後の受信 / repository_dispatch (oc-watchdog) に成功した最後の時刻
  lastWebhookAt?: number;
  lastDispatchAt?: number;
  // 直近の digest (oc-pm kind=digest) を試行した時刻。成功・失敗・dry-run の記録を問わず 24 時間に 1 回。
  digestAt?: number;
  // GitHub REST の x-ratelimit-* (ヘッダのあった値だけ更新する)。reset は epoch 秒。
  rest?: RateInfo;
  // 直近の reconcile で DO と REST が食い違った件数と、その累計
  reconcileDiff?: { last: number; total: number };
  rateGuardOn?: boolean;
  // VM の状態 (launched・relaunch・phase・pm_art) を取り込んだ時刻。IMPORT_REQUIRED=1 のときは、無いあいだ launch しない。
  importedAt?: string;
  // launch を止めている区間 (#2795)。止まっていない間は無い。/status.launch_halted と PM への通知に使う。
  halt?: Halt;
  // 同時実行の上限の推定 (saturation.ts)。観測の履歴は meta/obs に別に持つ。
  cap?: Cap;
  installationId?: number | null;
  lastPlan?: Plan;
  lastError?: { at: string; what: string };
  // 降格 (#2340)。値があると launch と dispatch は dry-run になる。解除は手動 (POST /demote/reset) か、60 分の時限復帰 (auto-stale)。
  demoted?: { at: string; reason: string };
  // 降格の判定を始めた時刻 (コードが最初に動いた時刻・解除した時刻)。これより前の /oc は判定の対象にしない (過去の二重投稿で止めない・解除前の組を再降格させない)。
  ocWatchFrom?: number;
  // 一覧を上限ページで打ち切った対象 (名前ごとに、同じ一覧を次に読んだ結果で上書きする)。1 件でもあれば fresh=false。
  syncTruncated?: Record<string, { pages: number; at: string }>;
  // 直近の全体同期の REST 回数 (全体 / うちコメント一覧)。
  fullSyncCalls?: number;
  fullSyncCommentCalls?: number;
  // 管理用の全体同期の時刻 (直近 1 時間の分だけ持つ)。
  resyncs?: number[];
  // 失敗した webhook 配送の回収 (#2339)。guid ごとの再配送の試行回数 (live のときだけ増える) と最後に触れた時刻。
  // 走査のたびに、一覧に失敗として残っている guid だけを残す。
  redeliver?: Record<string, { n: number; at: number }>;
  redeliverAt?: number;
  // 直近の走査で見た status != OK の配送の件数
  redeliverFailed?: number;
  // 率制限の判定 (#2345) の直近の評価。count / total は窓 (30 分) の件数、streak は条件を満たした評価の連続回数、alert は streak が RATE_STREAK 以上。
  rateAlert?: { at: number; count: number; total: number; streak: number; alert: boolean };
  counters?: {
    launched: number;
    dispatched: number;
    wouldLaunch: number;
    wouldDispatch: number;
    reconciles: number;
    pmDispatched?: number;
    wouldDispatchPm?: number;
    closed?: number;
    wouldClose?: number;
    // 再投入の意図 (oc-pm-intent: relaunch)。投稿した数・dry-run で記録した数・検査で拒否した数 (理由ごと)。
    intentLaunched?: number;
    intentWouldLaunch?: number;
    intentRejected?: Record<string, number>;
    redelivered?: number;
    wouldRedeliver?: number;
    // 停止行の直接の再投入 (wake・CI-250)。投稿した数と、dry-run で記録した数。
    wakeSent?: number;
    wouldWake?: number;
    demoted?: number;
    restored?: number;
  };
}

export interface Log {
  at: string;
  kind:
    | "would-launch"
    | "launch"
    | "would-dispatch"
    | "dispatch"
    | "would-wake"
    | "wake"
    | "would-pm-dispatch"
    | "pm-dispatch"
    | "would-close"
    | "close"
    | "error"
    | "skip"
    | "truncated"
    | "recovered"
    | "unobserved"
    | "observed"
    | "resync"
    | "would-redeliver"
    | "redeliver"
    | "rate-alert"
    | "import"
    | "demote"
    | "restore";
  n?: number;
  art?: string;
  note?: string;
}

const BUCKETS = ["issues", "prs", "runs", "botLast", "botReport", "pmArt", "blockedBy", "launchedAt", "sig", "rateRuns"] as const;

export function loadState(store: Store): PmState {
  const s: PmState = structuredClone(EMPTY_STATE);
  for (const b of BUCKETS) {
    for (const [k, v] of store.all(b)) (s as any)[b][k] = v;
  }
  return s;
}

// 参照が変わったキーだけを書く (applyEvent は変更したキーの値を新しいオブジェクトにする)。
export function persistDiff(prev: PmState, next: PmState, store: Store): void {
  for (const b of BUCKETS) {
    const p = (prev as any)[b] as Record<string, unknown>;
    const n = (next as any)[b] as Record<string, unknown>;
    if (p === n) continue;
    for (const k of Object.keys(n)) if (p[k] !== n[k]) store.put(b, k, n[k]);
    for (const k of Object.keys(p)) if (!(k in n)) store.del(b, k);
  }
}

const iso = (ms: number): string => new Date(ms).toISOString();
const ART_LINE_RE = /^\s*`?(oc_artifacts:[^\n`]*)`?\s*$/m;
// 分類に渡す bot 報告の要約 (先頭 400 字と oc_artifacts 行)。
const digestBot = (b: { at: string; body: string }): Snapshot["bot_last"][string] => {
  const am = ART_LINE_RE.exec(b.body);
  return { at: b.at, head: b.body.slice(0, 400), art: am ? am[1].trim() : null };
};

export interface EngineDeps {
  store: Store;
  cfg: Config;
  now: () => number;
  // App の installation token で認証した REST クライアント。未設定 (setup 前) なら null。
  gh: () => Promise<Gh | null>;
  // この App の bot ログイン (slug + "[bot]")。PM のコメントとして扱う。
  pmBotLogin: () => string | null;
  // status・ログから取り除く実行時の secret (webhook secret・PEM・token など)。
  secrets?: () => string[];
  // App の JWT で叩く REST (配送の一覧と再配送)。installation token の枠とは別なので、レート情報は持ち込まない。未設定なら再配送しない。
  app?: () => Promise<Gh | null>;
  // Workers Analytics Engine の書き込み口 (CI-230)。binding が無い環境 (dev・テスト) では未設定で、何も書かない。
  ae?: AeSink;
}

const COUNTED_BUCKETS = ["issues", "prs", "runs", "botLast", "pmArt", "launchedAt"] as const;

// updatedAt だけが違う更新は食い違いに数えない (コメントの追加などで REST の updated_at は webhook 無しでも進む)。
const sameIgnoringUpdatedAt = (a: unknown, b: unknown): boolean => {
  const strip = (v: unknown) => (v && typeof v === "object" ? { ...(v as object), updatedAt: undefined } : v);
  return JSON.stringify(strip(a)) === JSON.stringify(strip(b));
};

// REST を適用した結果、DO の内容が実際に変わった entity の数。
function countChanged(prev: PmState, next: PmState): number {
  let n = 0;
  for (const b of COUNTED_BUCKETS) {
    const p = prev[b] as Record<string, unknown>;
    const q = next[b] as Record<string, unknown>;
    if (p === q) continue;
    for (const k of Object.keys(q)) if (p[k] !== q[k] && !sameIgnoringUpdatedAt(p[k], q[k])) n++;
  }
  return n;
}

// queued として数える run の状態 (in_progress が running)。
const QUEUED_STATUSES = ["queued", "pending", "waiting"];

export class Engine {
  s: PmState;
  meta: Meta;
  log: Log[] = [];
  // tick ごとの run 数の観測 (24 時間)。上限の推定と /status の peak_running に使う。
  obs: Sample[];
  dirty = false;
  private busy = false;
  // この tick で /oc を投稿した数 (launch・再投入の意図・wake の合計)。room (TARGET − active) の残りを wake が見るため。
  private tickPosted = 0;
  private ocPosts: OcPost[];
  private wouldRecs: WouldRec[];

  private readonly d: EngineDeps;

  constructor(d: EngineDeps) {
    this.d = d;
    this.s = loadState(d.store);
    this.meta = d.store.get<Meta>("meta", "main") ?? {};
    this.log = d.store.get<Log[]>("meta", "log") ?? [];
    this.obs = d.store.get<Sample[]>("meta", "obs") ?? [];
    this.ocPosts = d.store.get<OcPost[]>("meta", "ocPosts") ?? [];
    this.wouldRecs = d.store.get<WouldRec[]>("meta", "wouldRecs") ?? [];
    if (this.meta.ocWatchFrom === undefined) {
      this.meta.ocWatchFrom = d.now();
      this.saveMeta();
    }
  }

  private saveMeta(): void {
    this.d.store.put("meta", "main", this.meta);
  }
  // 自由文は secret・token・PEM を取り除いてから、status とログに出す。
  private clean(s: string): string {
    return redact(s, this.d.secrets?.() ?? []);
  }
  private pushLog(l: Omit<Log, "at">): void {
    const entry = { at: iso(this.d.now()), ...l, ...(l.note === undefined ? {} : { note: this.clean(l.note) }) };
    this.log.push(entry);
    if (this.log.length > 60) this.log = this.log.slice(-60);
    this.d.store.put("meta", "log", this.log);
    console.log(JSON.stringify({ pm: entry.kind, n: entry.n, art: entry.art, note: entry.note }));
  }
  private setError(at: number, what: string): void {
    this.meta.lastError = { at: iso(at), what: this.clean(what) };
  }
  // Gh の全応答から呼ばれる。ヘッダのあった値だけ更新する (保存は次の saveMeta)。
  recordRate(r: RateInfo): void {
    this.meta.rest = { ...(this.meta.rest ?? {}), ...r };
  }
  private pmLogins(): string[] {
    const b = this.d.pmBotLogin();
    return b ? [...this.d.cfg.pmLogins, b] : this.d.cfg.pmLogins;
  }

  // ---------------------------------------------------------------- webhook
  // 署名の検証は handleWebhook の先頭で行う。検証に失敗したら state も store も変えない。
  receive(secret: string, event: string | null, signature: string | null, body: string): WebhookResult {
    const r = handleWebhook(this.s, {
      secret,
      event,
      signature,
      body,
      botLogin: this.d.cfg.botLogin,
      pmLogins: this.pmLogins(),
      reviewerLogin: this.d.cfg.reviewerLogin,
      markLogin: this.d.cfg.markLogin,
      repo: this.d.cfg.repo,
    });
    if (r.status === 202) this.meta.lastWebhookAt = this.d.now();
    if (r.status === 202 && r.reason === "applied" && r.state !== this.s) {
      persistDiff(this.s, r.state, this.d.store);
      this.s = r.state;
    }
    if (r.status === 202 && r.reason === "applied") this.dirty = true;
    if (r.status === 202 && r.reason === "applied" && event === "issue_comment") this.noteOc(JSON.parse(body));
    return r;
  }

  // ---------------------------------------------------------------- 降格と shadow (#2340)
  // PM のログイン (個人と PM App) の /oc 投稿を記録する。id で重複を除く (webhook と reconcile の両方から来るため)。
  // 降格の組は、Worker (PM App) と Worker 以外の PM ログイン (個人) の /oc だけ (先後は問わない)。Worker 同士・個人同士の組は数えない。
  // 組は OC_DOUBLE_MS 以内で同じ issue に付き、判定は ocWatchFrom 以降に届いたものだけ。
  private noteOc(p: any): void {
    const c = p?.comment;
    const n = Number(p?.issue?.number);
    const id = Number(c?.id);
    const at = Date.parse(c?.created_at);
    const login: string | undefined = c?.user?.login;
    if (p?.action !== "created" || !Number.isInteger(n) || !Number.isInteger(id) || !Number.isFinite(at)) return;
    if (!login || typeof c.body !== "string" || !this.pmLogins().includes(login) || !OC_RE.test(c.body)) return;
    if (this.ocPosts.some((x) => x.id === id)) return;
    const vm = this.d.cfg.pmLogins.includes(login);
    const from = this.meta.ocWatchFrom ?? 0;
    if (at >= from && this.ocPosts.some((x) => x.at >= from && x.n === n && x.vm !== vm && Math.abs(x.at - at) <= OC_DOUBLE_MS)) this.demote(`double-oc #${n}`);
    const now = this.d.now();
    this.ocPosts = [...this.ocPosts.filter((x) => x.at >= now - OC_KEEP_MS), { n, id, at, vm }];
    this.d.store.put("meta", "ocPosts", this.ocPosts);
  }

  private demote(reason: string): void {
    if (this.meta.demoted) return;
    this.meta.demoted = { at: iso(this.d.now()), reason: this.clean(reason) };
    this.meta.counters = this.meta.counters ?? this.zero();
    this.meta.counters.demoted = (this.meta.counters.demoted ?? 0) + 1;
    this.pushLog({ kind: "demote", note: reason });
    this.saveMeta();
  }

  // 降格の解除。手動 (POST /demote/reset・呼び出し側が repo の push 権限を確認してから呼ぶ) か、時限復帰 (auto-stale)。
  // 判定の起点を解除の時刻に移す。解除前の /oc の組は、full sync が読み直しても再判定しない。
  resetDemote(note: "manual" | "auto-stale" = "manual"): boolean {
    if (!this.meta.demoted) return false;
    this.meta.demoted = undefined;
    this.meta.ocWatchFrom = this.d.now();
    this.meta.counters = this.meta.counters ?? this.zero();
    this.meta.counters.restored = (this.meta.counters.restored ?? 0) + 1;
    this.pushLog({ kind: "restore", note });
    this.saveMeta();
    return true;
  }

  // 降格から DEMOTE_AUTO_LIFT_MS を超えたら、人の操作を待たずに解除する (時限復帰)。
  private autoLiftStaleDemote(): void {
    const at = this.meta.demoted ? Date.parse(this.meta.demoted.at) : NaN;
    if (Number.isFinite(at) && this.d.now() - at > DEMOTE_AUTO_LIFT_MS) this.resetDemote("auto-stale");
  }

  // 投稿・dispatch の実効モード。設定が live でも、降格中は dry-run。
  private launchLive(): boolean {
    return this.d.cfg.liveLaunch && !this.meta.demoted;
  }
  private dispatchLive(): boolean {
    return this.d.cfg.liveDispatch && !this.meta.demoted;
  }

  // 直近 SHADOW_WINDOW_MS の would_launch (計画) と、VM (PM の個人アカウント) の /oc を突き合わせる。個票は出さず、issue 番号だけ。
  // recall = VM が投稿した各 issue が、投稿の直前 15 分以内の would_launch に含まれていた割合。
  // precision = would_launch の (tick, issue) のうち、15 分以内に VM が同じ issue を投稿した割合。投稿 0 件の窓では null。
  shadow(): Record<string, unknown> {
    const now = this.d.now();
    const ws = now - SHADOW_WINDOW_MS;
    const W = SHADOW_WINDOW_MS;
    const vm = this.ocPosts.filter((x) => x.vm && x.at >= ws && x.at <= now);
    const recs = this.wouldRecs.filter((w) => w.at >= ws - W && w.at <= now);
    const hit = (p: OcPost) => recs.some((w) => w.at >= p.at - W && w.at <= p.at && w.ns.includes(p.n));
    const pairs = recs.filter((w) => w.at >= ws).flatMap((w) => w.ns.map((n) => ({ n, at: w.at })));
    const posted = (q: { n: number; at: number }) => vm.some((p) => p.n === q.n && p.at >= q.at && p.at <= q.at + W);
    const recallHit = vm.filter(hit).length;
    const precHit = pairs.filter(posted).length;
    const uniq = (xs: number[]) => [...new Set(xs)].sort((a, b) => a - b);
    return {
      window_start: iso(ws),
      posts: vm.length,
      recall: vm.length ? recallHit / vm.length : null,
      precision: pairs.length ? precHit / pairs.length : null,
      vm_only: uniq(vm.filter((p) => !hit(p)).map((p) => p.n)),
      worker_only: uniq(pairs.filter((q) => !posted(q)).map((q) => q.n)),
    };
  }

  // ---------------------------------------------------------------- 同期
  // 戻り値は、DO の内容が実際に変わった entity の数 (reconcile の食い違いの計数に使う)。
  private applyAll(event: (typeof WEBHOOK_EVENTS)[number], payload: unknown): number {
    if (event === "issue_comment") this.noteOc(payload);
    const next = applyEvent(this.s, event, payload as any, this.d.cfg.botLogin, this.pmLogins(), this.d.cfg.reviewerLogin, this.d.cfg.markLogin);
    if (next === this.s) return 0;
    const changed = countChanged(this.s, next);
    persistDiff(this.s, next, this.d.store);
    this.s = next;
    return changed;
  }

  // 一覧の結果を記録する。打ち切りは対象名ごとに meta へ残し (本文・題名は入れない)、同じ一覧を次に読んで打ち切りが無ければ消す。
  private note<T>(name: string, r: ListResult<T>): ListResult<T> {
    const t = { ...(this.meta.syncTruncated ?? {}) };
    const was = name in t;
    if (r.truncated) {
      t[name] = { pages: r.pages, at: iso(this.d.now()) };
      if (!was) this.pushLog({ kind: "truncated", note: `${name} pages=${r.pages}` });
    } else if (was) {
      delete t[name];
      this.pushLog({ kind: "recovered", note: name });
    }
    this.meta.syncTruncated = Object.keys(t).length ? t : undefined;
    return r;
  }

  async fullSync(gh: Gh): Promise<void> {
    const R = this.d.cfg.repo;
    const startedAt = this.d.now();
    const calls0 = gh.calls;
    const issues = this.note("issues_open", await gh.list<any>(`/repos/${R}/issues?state=open`, 30));
    const openNums = new Set<number>();
    for (const i of issues.items) {
      if (i.pull_request) continue;
      openNums.add(i.number);
      this.applyAll("issues", { issue: i });
    }
    // 打ち切ったときは、一覧に無いことが close の証拠にならないので、close したとみなさない。
    if (!issues.truncated) {
      for (const [k, v] of Object.entries(this.s.issues)) {
        if (v.state === "open" && !openNums.has(Number(k))) {
          const next: IssueState = { ...v, state: "closed", labels: [], body: "", updatedAt: iso(this.d.now()) };
          this.d.store.put("issues", k, next);
          this.s = { ...this.s, issues: { ...this.s.issues, [k]: next } };
        }
      }
    }
    // PR は open を全件、closed は窓の中 (更新が新しい順に読み、窓より古いところで止める) だけ読む。state=all の全件は PR の増加で上限を超える。
    const prsOpen = this.note("pulls_open", await gh.list<any>(`/repos/${R}/pulls?state=open`, 30));
    const sinceMs = startedAt - this.d.cfg.commentWindowH * 3_600_000;
    const prsClosed = this.note(
      "pulls_closed",
      await gh.list<any>(`/repos/${R}/pulls?state=closed&sort=updated&direction=desc`, 30, undefined, (p) => Date.parse(p.updated_at) < sinceMs),
    );
    for (const p of [...prsClosed.items, ...prsOpen.items]) this.applyAll("pull_request", { pull_request: p });
    if (!prsOpen.truncated) {
      const openPrs = new Set(prsOpen.items.map((p) => String(p.number)));
      for (const [k, v] of Object.entries(this.s.prs)) {
        if (v.state === "open" && !openPrs.has(k)) {
          const next: PrState = { ...v, state: "closed", body: "", updatedAt: iso(this.d.now()) };
          this.d.store.put("prs", k, next);
          this.s = { ...this.s, prs: { ...this.s.prs, [k]: next } };
        }
      }
    }
    await this.syncRuns(gh);
    const c0 = gh.calls;
    await this.syncComments(gh, sinceMs);
    this.meta.fullSyncCommentCalls = gh.calls - c0;
    await this.syncBlockers(gh, 80);
    await this.syncSignals(gh);
    this.meta.fullSyncCalls = gh.calls - calls0;
    // reconcile の起点は同期の開始時刻 (同期中に作られたコメントを次の reconcile が読み直す)。
    this.meta.fullSyncAt = this.d.now();
    this.meta.signalVer = SIGNAL_VER;
    this.meta.reconcileAt = startedAt;
    this.saveMeta();
  }

  // 管理用の全体同期 (POST /admin/resync)。REST の内容で派生状態を作り直す (fullSync と同じ。ページ上限も同じ)。
  // 永続状態 (launchedAt・relaunch・planned・phase・counters) は同期が触らないので残る。busy の間 (tick と同時) は走らせない。
  async resync(gh: Gh): Promise<{ status: "ok" } | { status: "limited"; retryAfterS: number } | { status: "busy" }> {
    if (this.busy) return { status: "busy" };
    const now = this.d.now();
    const recent = (this.meta.resyncs ?? []).filter((t) => now - t < HOUR_MS);
    if (recent.length >= RESYNC_PER_HOUR) return { status: "limited", retryAfterS: Math.ceil((recent[0] + HOUR_MS - now) / 1000) };
    this.meta.resyncs = [...recent, now];
    this.saveMeta();
    this.busy = true;
    try {
      await this.fullSync(gh);
      this.pushLog({ kind: "resync", note: "ok" });
    } catch (e) {
      this.setError(now, e instanceof GhError ? e.message : "resync failed");
      this.pushLog({ kind: "error", note: this.meta.lastError?.what });
      this.saveMeta();
      throw e;
    } finally {
      this.busy = false;
    }
    return { status: "ok" };
  }

  // ---------------------------------------------------------------- VM の状態の取り込み・書き出し (#2343)
  // apply のときだけ書く (既定は検証のみ。呼び出し側で検証を済ませた値が来る)。同じ issue が両方にあるときは、
  // 新しい時刻 (launched・pm_art) と多い回数 (relaunch) を残す。phase は取り込んだ値 (VM の現在値) にする。
  importVm(v: VmState, apply: boolean): void {
    if (!apply) return;
    for (const [k, at] of Object.entries(v.launched)) {
      const cur = this.s.launchedAt[k];
      if (cur && Date.parse(cur) >= Date.parse(at)) continue;
      this.d.store.put("launchedAt", k, at);
      this.s = { ...this.s, launchedAt: { ...this.s.launchedAt, [k]: at } };
    }
    for (const [k, r] of Object.entries(v.relaunch)) {
      const cur = this.d.store.get<{ count: number; art: string | null }>("relaunch", k);
      if (!cur || cur.count < r.count) this.d.store.put("relaunch", k, { count: r.count, art: r.art });
    }
    for (const [k, p] of Object.entries(v.pm_art)) {
      const cur = this.s.pmArt[k];
      if (cur && Date.parse(cur.at) >= Date.parse(p.at)) continue;
      const next = { at: p.at, line: p.line };
      this.d.store.put("pmArt", k, next);
      this.s = { ...this.s, pmArt: { ...this.s.pmArt, [k]: next } };
    }
    this.d.store.put("meta", "phase", v.phase);
    this.meta.importedAt = iso(this.d.now());
    this.saveMeta();
    this.pushLog({ kind: "import", note: `launched ${Object.keys(v.launched).length} relaunch ${Object.keys(v.relaunch).length} pm_art ${Object.keys(v.pm_art).length}` });
  }

  // VM の形式 (launched.json・relaunch.json・phase.json と pm_art) で書き出す。relaunch は issue 番号のキーだけ (np:<n> は VM に無いので出さない)。
  // phase は一度も保存していなければ null (最初の tick の前)。
  exportVm(): Omit<VmState, "phase"> & { phase: VmState["phase"] | null } {
    const launched = { ...this.s.launchedAt };
    const relaunch: VmState["relaunch"] = {};
    for (const [k, r] of this.d.store.all<{ count: number; art: string | null }>("relaunch")) {
      if (/^[1-9]\d*$/.test(k)) relaunch[k] = { count: r.count, art: r.art };
    }
    const pm_art: VmState["pm_art"] = {};
    for (const [k, p] of Object.entries(this.s.pmArt)) pm_art[k] = { at: p.at, line: p.line };
    const phase = this.d.store.get<VmState["phase"]>("meta", "phase") ?? null;
    return { launched, relaunch, phase, pm_art };
  }

  private async syncRuns(gh: Gh): Promise<number> {
    const R = this.d.cfg.repo;
    let diff = 0;
    const seen = new Set<string>();
    let truncated = false;
    for (const st of ["requested", "in_progress", "queued", "pending", "waiting"]) {
      const runs = this.note(`runs_${st}`, await gh.list<any>(`/repos/${R}/actions/runs?status=${st}`, 3, (j) => j?.workflow_runs ?? []));
      truncated ||= runs.truncated;
      for (const w of runs.items) {
        seen.add(String(w.id));
        diff += this.applyAll("workflow_run", { workflow_run: w });
      }
    }
    // 完了を取りこぼした run (webhook 欠落) は、一覧に無ければ completed とみなす。打ち切ったときは一覧に無いことが証拠にならない。
    if (truncated) return diff;
    for (const [k, v] of Object.entries(this.s.runs)) {
      if (v.status !== "completed" && !seen.has(k)) {
        const next: RunState = { ...v, status: "completed", conclusion: v.conclusion ?? "unknown" };
        this.d.store.put("runs", k, next);
        this.s = { ...this.s, runs: { ...this.s.runs, [k]: next } };
        diff++;
      }
    }
    return diff;
  }

  // コメントは新しい順に読み、created_at が窓より古いコメントに達したら止める (読む量は窓内の件数で決まる)。
  // 上限ページで窓の端に届かなかったら打ち切りとして記録する (fresh=false)。適用は created_at の最新が残るので順序に依らない。
  private async syncComments(gh: Gh, sinceMs: number): Promise<number> {
    const R = this.d.cfg.repo;
    let diff = 0;
    // 一覧は 1 回に数千件になるので、状態に使うコメント (bot・reviewer と PM) 以外は本文を持たない。reviewer は webhook 経路と同じマーカーを読むため含める。
    // 停止印の作者 (markLogin) も同じ理由で含める。型 (user.type) は webhook 経路と同じ判定 (停止印は型 Bot を要る) のため残す (#2639)。
    // 人の /oc は本文で『着手であって応答ではない』と判定する (webhook.ts の answered) ので、/oc で始まる本文だけは残す。
    const mine = new Set([this.d.cfg.botLogin, this.d.cfg.reviewerLogin, this.d.cfg.markLogin, ...this.pmLogins()]);
    const keepBody = (c: any) => mine.has(c.user?.login) || /^\/oc\b/m.test(c.body ?? "");
    const slim = (c: any) => ({ id: c.id, issue_url: c.issue_url, created_at: c.created_at, user: { login: c.user?.login, type: c.user?.type }, author_association: c.author_association, body: keepBody(c) ? c.body : "" });
    const cs = this.note(
      "comments",
      await gh.list<any>(
        `/repos/${R}/issues/comments?sort=created&direction=desc`,
        this.d.cfg.commentMaxPages,
        (j) => (Array.isArray(j) ? j.map(slim) : []),
        (c) => Date.parse(c.created_at) < sinceMs,
      ),
    );
    for (const c of cs.items) {
      const n = Number(String(c.issue_url).split("/").pop());
      if (!Number.isInteger(n)) continue;
      diff += this.applyAll("issue_comment", { action: "created", comment: c, issue: { number: n } });
    }
    return diff;
  }

  // blocked_by の一覧が不明な issue (件数が一覧の件数より多い: 無いか、件数だけ更新されて古い) を REST で取る。1 回の上限 max 件。
  private async syncBlockers(gh: Gh, max: number): Promise<void> {
    const R = this.d.cfg.repo;
    let left = max;
    let read = 0;
    let truncated = false;
    let pages = 0;
    for (const [k, v] of Object.entries(this.s.issues)) {
      if (left <= 0) break;
      if (v.state !== "open" || v.blockedByCount <= (this.s.blockedBy[k]?.length ?? 0)) continue;
      left--;
      read++;
      const j = await gh.list<any>(`/repos/${R}/issues/${k}/dependencies/blocked_by`, 3);
      pages = Math.max(pages, j.pages);
      // 打ち切った一覧は持たない (一部だけ持つと、残りの blocker を見落として着手する)。不明のままなら着手しない。
      if (j.truncated) {
        truncated = true;
        continue;
      }
      // closed の blocker も含めて全件を持つ。open かどうかは分類側が issue の状態で判断する。
      const all = j.items.map((x) => x.number as number).sort((a, b) => a - b);
      this.d.store.put("blockedBy", k, all);
      this.s = { ...this.s, blockedBy: { ...this.s.blockedBy, [k]: all } };
    }
    if (read > 0) this.note("blocked_by", { items: [], truncated, pages });
  }

  // oc-pm の検出に要る手がかりのうち、webhook だけでは埋まらないものを REST で補う (best effort: 失敗しても同期は続ける)。
  //  - open PR の reviewer verdict (一度だけ。以後は pull_request_review の配送で更新)
  //  - needs-user-input が付いた時刻 (issue events の labeled)
  private async syncSignals(gh: Gh): Promise<void> {
    const R = this.d.cfg.repo;
    const reviewer = this.d.cfg.reviewerLogin;
    const commit = (next: PmState): void => {
      if (next === this.s) return;
      persistDiff(this.s, next, this.d.store);
      this.s = next;
    };
    let left = 30;
    for (const p of Object.values(this.s.prs)) {
      if (left <= 0) break;
      if (p.state !== "open" || this.s.sig[String(p.number)]?.revChecked) continue;
      left--;
      try {
        const rs = await gh.list<any>(`/repos/${R}/pulls/${p.number}/reviews`, 3);
        let next = this.s;
        for (const r of rs.items) next = reviewSignal(next, p.number, r, reviewer);
        commit(setSig(next, String(p.number), { revChecked: true }));
      } catch (e) {
        if (e instanceof GhError && (e.status === 403 || e.status === 429)) break;
      }
    }
    left = 20;
    for (const i of Object.values(this.s.issues)) {
      if (left <= 0) break;
      if (i.state !== "open" || !i.labels.includes(NEEDS_USER_LABEL) || this.s.sig[String(i.number)]?.labelAt) continue;
      left--;
      try {
        const evs = await gh.list<any>(`/repos/${R}/issues/${i.number}/events`, 3);
        const last = evs.items.filter((e) => e?.event === "labeled" && e?.label?.name === NEEDS_USER_LABEL).pop();
        // events に無いときは、最後の更新時刻を起点にする (回答の見落としより、誤検出を避ける側に倒す)
        commit(setSig(this.s, String(i.number), { labelAt: typeof last?.created_at === "string" ? last.created_at : i.updatedAt }));
      } catch (e) {
        if (e instanceof GhError && (e.status === 403 || e.status === 429)) break;
      }
    }
  }

  // webhook 欠落への備え: run の全件・直近更新の issue / PR / コメントだけを REST で突き合わせる。
  async reconcile(gh: Gh): Promise<void> {
    const R = this.d.cfg.repo;
    const since = (this.meta.reconcileAt ?? this.d.now() - 3_600_000) - 120_000;
    // 食い違い = REST を適用して DO の内容が変わった entity (webhook の欠落・遅延の指標。個票は残さず件数だけ)。
    let diff = await this.syncRuns(gh);
    const issues = this.note("issues_updated", await gh.list<any>(`/repos/${R}/issues?state=all&since=${encodeURIComponent(iso(since))}&sort=updated`, 5));
    for (const i of issues.items) if (!i.pull_request) diff += this.applyAll("issues", { issue: i });
    const prs = this.note(
      "pulls_updated",
      await gh.list<any>(`/repos/${R}/pulls?state=all&sort=updated&direction=desc`, 5, undefined, (p) => Date.parse(p.updated_at) < since),
    );
    for (const p of prs.items) diff += this.applyAll("pull_request", { pull_request: p });
    diff += await this.syncComments(gh, since);
    await this.syncBlockers(gh, 30);
    await this.syncSignals(gh);
    this.prune();
    this.meta.reconcileDiff = { last: diff, total: (this.meta.reconcileDiff?.total ?? 0) + diff };
    this.meta.reconcileAt = this.d.now();
    this.meta.counters = { ...(this.meta.counters ?? this.zero()), reconciles: (this.meta.counters?.reconciles ?? 0) + 1 };
    this.saveMeta();
  }

  private zero(): NonNullable<Meta["counters"]> {
    return { launched: 0, dispatched: 0, wouldLaunch: 0, wouldDispatch: 0, reconciles: 0, pmDispatched: 0, wouldDispatchPm: 0, closed: 0, wouldClose: 0, redelivered: 0, wouldRedeliver: 0, demoted: 0, restored: 0 };
  }

  // 完了して 1 時間たった run は捨てる (順不同配送の判定に使う期間だけ持つ)。
  private prune(): void {
    const cut = this.d.now() - 3_600_000;
    for (const [k, v] of Object.entries(this.s.runs)) {
      if (v.status === "completed" && Date.parse(v.updatedAt) < cut) {
        this.d.store.del("runs", k);
        const { [k]: _, ...rest } = this.s.runs;
        this.s = { ...this.s, runs: rest };
      }
    }
    // 率制限のマーカーは run と同じ 1 時間で捨てる (判定の窓は 30 分)。
    for (const [k, v] of Object.entries(this.s.rateRuns)) {
      if (Date.parse(v.at) < cut) {
        this.d.store.del("rateRuns", k);
        const { [k]: _, ...rest } = this.s.rateRuns;
        this.s = { ...this.s, rateRuns: rest };
      }
    }
    // 閉じた issue / PR の手がかりは使わない。数えた run の id (killRun) だけは残す (reopen の後に古い run の配送が届いても数え直さない)。
    for (const k of Object.keys(this.s.sig)) {
      const i = this.s.issues[k];
      const p = this.s.prs[k];
      if (!((i || p) && i?.state !== "open" && p?.state !== "open")) continue;
      const killRun = this.s.sig[k].killRun;
      const subParent = this.s.sig[k].subParent;
      const kept = { ...(killRun === undefined ? {} : { killRun }), ...(subParent === undefined ? {} : { subParent }) };
      const keep = Object.keys(kept).length ? kept : undefined;
      if (JSON.stringify(keep) === JSON.stringify(this.s.sig[k])) continue;
      if (keep) this.d.store.put("sig", k, keep);
      else this.d.store.del("sig", k);
      const { [k]: _, ...rest } = this.s.sig;
      this.s = { ...this.s, sig: keep ? { ...rest, [k]: keep } : rest };
    }
  }

  // ---------------------------------------------------------------- 分類と計画
  snapshot(): { snap: Snapshot; input: ClassifyInput; unknown: Set<number> } {
    const s = this.s;
    const issues = Object.values(s.issues)
      .filter((i) => i.state === "open")
      .map((i) => ({ number: i.number, title: i.title, labels: i.labels, body: i.body, deps: { total_blocked_by: i.blockedByCount }, ...(i.artLine ? { artLine: i.artLine } : {}), subParent: s.sig[String(i.number)]?.subParent?.n ?? null }));
    const prs = (Object.values(s.prs) as PrState[]).map((p) => ({ number: p.number, state: p.state, ref: p.ref, body: p.body }));
    const runs = (Object.values(s.runs) as RunState[])
      .filter((r) => r.status !== "completed")
      .map((r) => ({ id: r.id, event: r.event, title: r.title }));
    const bot_last: Snapshot["bot_last"] = {};
    for (const [k, b] of Object.entries(s.botLast)) bot_last[k] = digestBot(b);
    const bot_report: Snapshot["bot_report"] = {};
    for (const [k, b] of Object.entries(s.botReport)) bot_report[k] = digestBot(b);
    // 停止判定 (run-outcome を除く) は botLast の本文で見る。素材名は直前の報告 (botReport) から読む。無い (古い保存値) issue は空 = 新しい素材なし。
    const fullBotBody: Record<string, string> = {};
    for (const [k, b] of Object.entries(s.botLast)) fullBotBody[k] = b.body;
    const reportBody: Record<string, string> = {};
    for (const [k, b] of Object.entries(s.botReport)) reportBody[k] = b.body;
    // 最後の run-outcome の reason (webhook が sig に保存する)。
    const outcomeReason: Record<string, string> = {};
    for (const [k, g] of Object.entries(s.sig)) if (g.outcome) outcomeReason[k] = g.outcome.reason;
    const liveBlockers: Record<string, number[]> = {};
    const unknown = new Set<number>();
    for (const i of issues) {
      if ((i.deps?.total_blocked_by ?? 0) > 0) {
        const lb = s.blockedBy[String(i.number)];
        if (lb) liveBlockers[String(i.number)] = lb;
        else {
          liveBlockers[String(i.number)] = [];
          unknown.add(i.number);
        }
      }
    }
    const relaunch: ClassifyInput["relaunch"] = {};
    for (const [k, v] of this.d.store.all<{ count: number; art: string | null }>("relaunch")) relaunch[k] = v;
    const pmAt: Record<string, string> = {};
    for (const [k, g] of Object.entries(s.sig)) if (g.pmAt) pmAt[k] = g.pmAt;
    const launchState: Record<string, LaunchState> = {};
    const launchDoneAt: Record<string, string> = {};
    for (const [k, v] of this.d.store.all<LaunchObs>("launchObs")) {
      launchState[k] = v.state;
      if (v.state === "observed" && v.doneAt !== undefined) launchDoneAt[k] = v.doneAt;
    }
    return {
      snap: { issues, prs, runs, bot_last, bot_report, pm_art: s.pmArt },
      input: { nowMs: this.d.now(), launched: s.launchedAt, launchState, launchDoneAt, relaunch, manualDeps: this.d.cfg.manualDeps, liveBlockers, fullBotBody, reportBody, outcomeReason, pmAt },
      unknown,
    };
  }

  private noPrState(n: number): NoPrCount {
    return { count: 0, unknown: 0, artifact: 0, art: null, ...this.d.store.get<NoPrCount>("relaunch", `np:${n}`) };
  }

  // 報告の新しい素材 (#3185): 直前の報告 (botReport) の素材名 (allowlist 内) のうち、直近の再投入の行 (無ければ既定の行) に無いもの。無ければ null。
  // 報告が無い (古い保存値) は素材名が取れないので null。停止報告かどうかは見ない (呼び出し側が見る)。
  private artExtra(n: number): string | null {
    const i = this.s.issues[String(n)];
    const base = this.noPrState(n).art ?? defaultArtLine(this.s.pmArt[String(n)]?.line, i?.artLine, i?.title ?? "", i?.labels ?? []);
    return addArts(base, neededArtsOf(this.s.botReport[String(n)]?.body ?? ""));
  }

  // opencode.yaml の未完了の run の計数 (active.ts)。room の基準は all。
  activeRuns(): ActiveCount {
    return countOpencodeRuns(Object.values(this.s.runs));
  }

  countActive(): number {
    return this.activeRuns().all;
  }

  // 打ち切りが連続して自動の再着手を止めた open な issue と、その回数 (番号順)。
  killedIssues(): Array<[number, number]> {
    const out: Array<[number, number]> = [];
    for (const i of Object.values(this.s.issues)) {
      const c = this.s.sig[String(i.number)]?.kill?.count ?? 0;
      if (i.state === "open" && c >= KILLED_STOP_AT) out.push([i.number, c]);
    }
    return out.sort((a, b) => a[0] - b[0]);
  }

  // 全 event の run を状態別に数える (running = in_progress、queued = queued・pending・waiting)。
  // oldestMin は最も古い queued の経過分 (queued に入った時刻の近似として updatedAt を使う)。queued が無ければ null。
  runCounts(now: number): { running: number; queued: number; oldestMin: number | null } {
    let running = 0;
    let queued = 0;
    let oldest = Infinity;
    for (const r of Object.values(this.s.runs)) {
      if (r.status === "in_progress") running++;
      else if (QUEUED_STATUSES.includes(r.status)) {
        queued++;
        const t = Date.parse(r.updatedAt);
        if (Number.isFinite(t) && t < oldest) oldest = t;
      }
    }
    return { running, queued, oldestMin: queued && Number.isFinite(oldest) ? Math.max(0, Math.floor((now - oldest) / 60_000)) : null };
  }

  // 1 回の観測 (tick ごと)。run 数を 1 分単位で記録し、同時実行の上限の推定を更新する。副作用は DO の保存だけ (GitHub へは書かない)。
  observe(now: number): void {
    const { running, queued } = this.runCounts(now);
    this.obs = appendSample(this.obs, { t: now, r: running, q: queued }, now);
    this.d.store.put("meta", "obs", this.obs);
    this.meta.cap = nextCap(this.meta.cap, this.obs, now);
  }

  // 規則は launch_issues.py の classify に、次の 3 点だけ足す (どれも本文を解析しない)。
  //  1. blocked_by の一覧が不明な issue は着手しない (誤着手より遅れを選ぶ)。
  //  2. open な子を持つ親 issue は着手対象から外す。
  //  3. ラベル oc:no-pr の issue は『PR を出さずに終わった』run の後。cooldown が過ぎるまで recent、過ぎたら再着手してよい
  //     (上限 NO_PR_MAX_RELAUNCH 回。超えたら stopped で人の判断に回す)。oc:stuck は user (人の判断待ち) に置く。
  plan(): { rows: Rows; plan: Plan; picks: Planned[]; unknown: Set<number>; children: Record<string, number[]>; stopBasis: Map<number, string> } {
    const { snap, input, unknown } = this.snapshot();
    const { rows, children, stopBasis } = classify(snap, input);
    const labels = new Map(snap.issues.map((i) => [i.number, i.labels] as const));
    const title = new Map(snap.issues.map((i) => [i.number, i.title] as const));
    const prios = this.prioMap();
    const nowMs = this.d.now();
    const cool = (n: number) => noPrCooldownMs(prios.get(n) ?? "normal", this.d.cfg.noPrCooldownH);
    const hasLabel = (n: number, l: string) => (labels.get(n) ?? []).includes(l);
    // pm-apply・needs-user-input は着手も再投入もしない (下の HOLD_LABELS の処理で user に置く)。
    const held = (n: number) => (labels.get(n) ?? []).some((l) => HOLD_LABELS.includes(l));
    const failed = (n: number): boolean => input.launchState?.[String(n)] === "failed";
    // 既定の素材行 (PM の行 → 本文の行 → 推定)。picks の既定と同じ。
    const artOf = new Map(snap.issues.map((i) => [i.number, i.artLine] as const));
    const baseArt = (n: number): string => defaultArtLine(this.s.pmArt[String(n)]?.line, artOf.get(n), title.get(n) ?? "", labels.get(n) ?? []);

    const moveTo = (n: number, from: keyof Rows, to: () => void) => {
      (rows as any)[from] = (rows as any)[from].filter((x: any) => (Array.isArray(x) ? x[0] : x) !== n);
      to();
    };

    // oc:no-pr の issue は、最後の oc-run-outcome の reason で再着手を決める (PR を出さずに終わった run の後だけ)。
    //  unknown: cooldown の後に 1 回だけ。artifact: 前回の oc_artifacts に無い allowlist 内の素材を足して 1 回。
    //    足す素材が無い artifact (#3185) は unknown と同じ扱い: cooldown の後に 1 回だけ (unknown の枠を使い、素材は前回の行のまま。本文に再確認の行を足す)。
    //    その再投入の後も素材なしで終われば、no_pr として PM agent (detectPm) に回す (detectPmTargets の artSpent)。
    //  blocked: blocker が 0 になった後に、その報告につき 1 回だけ (blocker が open の間は blocked の行に置かれ、ここには来ない)。
    //    同じ報告で一度再着手したら、blocker が再び付いて解除されても再着手しない (新しい報告が出るまで stopped に残る)。
    //  stop・split は PM agent (detectPm) に回す。
    const npPick = new Map<number, { art: string; np: NoPrReason; reportAt?: string; recheck?: boolean }>();
    const noPr = (n: number, from: "ready" | "stopped"): void => {
      const outcome = this.s.sig[String(n)]?.outcome;
      const reason = outcome?.reason ?? "unknown";
      const c = this.noPrState(n);
      const extra = reason === "artifact" ? this.artExtra(n) : null;
      let pick: { art: string; np: NoPrReason; reportAt?: string; recheck?: boolean } | null = null;
      let recent = false;
      let note = reason;
      if (reason === "stop" || reason === "split") {
        // PM agent の判断待ち (stopped に残す)。
      } else if (nowMs - this.lastAct(n) < cool(n)) {
        recent = true;
        note = "oc:no-pr cooldown";
      } else if (c.count >= NO_PR_MAX_RELAUNCH) {
        note = "oc:no-pr x" + c.count;
      } else if (reason === "blocked") {
        if (outcome?.at && c.blocked === outcome.at) note = "oc:no-pr blocked 再着手済み";
        else pick = { art: c.art ?? baseArt(n), np: "blocked", reportAt: outcome?.at };
      } else if (extra !== null) {
        // 報告に新しい素材がある。素材を足して 1 回だけ。停止報告のときだけ (報告の素材名を読む)。
        const rep = snap.bot_report[String(n)];
        if (c.artifact === 0 && isStopReport(rep?.head ?? "")) pick = { art: extra, np: "artifact" };
        else note = c.artifact === 0 ? "artifact: 停止報告でない" : `oc:no-pr ${reason} 再投入済み`;
      } else if (reason === "unknown" && c.unknown === 0) {
        pick = { art: baseArt(n), np: "unknown" };
      } else if (reason === "artifact" && c.unknown === 0) {
        // 新しい素材の無い artifact (報告が無い古い保存値を含む)。unknown の枠で 1 回。素材は前回の行 (無ければ既定) のまま。
        pick = { art: c.art ?? baseArt(n), np: "unknown", recheck: true };
      } else if (reason === "artifact") {
        note = "artifact: 新しい素材なし";
      } else {
        note = `oc:no-pr ${reason} 再投入済み`;
      }
      if (pick) {
        if (from === "stopped") moveTo(n, "stopped", () => rows.ready.push(n));
        npPick.set(n, pick);
      } else if (from === "ready") {
        if (recent) moveTo(n, "ready", () => rows.recent.push([n, note]));
        else moveTo(n, "ready", () => {
          rows.stopped.push([n, note]);
          stopBasis.set(n, `run-outcome reason=${reason}`);
        });
      }
    };

    for (const n of [...rows.ready]) {
      const kids = children[String(n)] ?? [];
      if (unknown.has(n)) moveTo(n, "ready", () => rows.blocked.push([n, []]));
      else if (kids.length) moveTo(n, "ready", () => rows.blocked.push([n, [...kids].sort((a, b) => a - b)]));
      else if (hasLabel(n, "oc:stuck")) moveTo(n, "ready", () => rows.user.push([n, "oc:stuck"]));
      else if (hasLabel(n, "oc:no-pr") && !held(n)) noPr(n, "ready");
    }
    for (const [n] of [...rows.relaunch]) {
      if ((children[String(n)] ?? []).length || hasLabel(n, "oc:stuck")) moveTo(n, "relaunch", () => {
        rows.stopped.push([n, "parent/stuck"]);
        stopBasis.set(n, "親の子あり または oc:stuck");
      });
    }
    // 親 (open な子を持つ) で、分類上 started / stopped / recent に入っているものは、そのままにする (着手対象ではないため)。
    for (const [n] of [...rows.stopped]) {
      if (!hasLabel(n, "oc:no-pr") || (children[String(n)] ?? []).length || unknown.has(n)) continue;
      // hold のラベルは再投入せず user に置く (ready に戻して下の hold の処理で移す)。観測できなかった投稿 (failed) は再投稿しない。
      if (held(n)) moveTo(n, "stopped", () => rows.ready.push(n));
      else if (!hasLabel(n, "oc:stuck") && !failed(n)) noPr(n, "stopped");
    }

    // 着手しても PR を出さない/出せない issue (pm-apply・needs-user-input) は、着手も再投入もしない。
    for (const n of [...rows.ready, ...rows.relaunch.map(([x]) => x)]) {
      const hold = (labels.get(n) ?? []).find((l) => HOLD_LABELS.includes(l));
      if (!hold) continue;
      moveTo(n, "ready", () => {});
      moveTo(n, "relaunch", () => {});
      rows.user.push([n, hold]);
    }

    // 実装 run が PR も出さずに連続して打ち切られた issue (webhook.ts の applyKill が数える sig.kill) は、自動で再着手しない。oc:no-pr の標識は付かない
    // (runner の shutdown では record-run-outcome.sh が走らない) ので、cooldown や再投入の枠には載せず stopped に置き、PM agent (oc-pm の no_pr) に回す。
    for (const [n, c] of this.killedIssues()) {
      const from = (["ready", "relaunch", "recent"] as const).find((r) => (rows[r] as unknown[]).some((x) => (Array.isArray(x) ? x[0] : x) === n));
      if (from) moveTo(n, from, () => {
        rows.stopped.push([n, `killed x${c}`]);
        stopBasis.set(n, "実装 run の連続打ち切り (kill)");
      });
    }

    const blocksCount = new Map<number, number>();
    const cls = classify(snap, input);
    for (const [k, v] of Object.entries(cls.blocksCount)) blocksCount.set(Number(k), v);
    const ready = rows.ready.map((n) => ({ n, title: title.get(n) ?? "", blocksCount: blocksCount.get(n) ?? 0, prio: prios.get(n) ?? "normal" }));
    const act = this.activeRuns();
    const active = act.all;
    // 推定の上限が無ければ TARGET のまま (変えない)。推定があれば、上限 + 余裕 (下限 TARGET_MIN、上限 TARGET)。
    const capEst = capValue(this.meta.cap, nowMs);
    const teff = targetEff(capEst, this.d.cfg.target, this.d.cfg.queueMargin, this.d.cfg.targetMin);
    // prio:low の上限 (LOW_CAP)。着手済み (started)・launch 可能 (ready・relaunch) で blocked でない prio:critical が 1 件以上ある間だけ効く。
    // 数えるのは未完了の run (実行中と待ち)。実行中の run は止めず、新しい low の launch だけを抑える。
    const activeByPrio = countRunsByPrio(Object.values(this.s.runs), Object.values(this.s.issues).map((i) => ({ title: i.title, prio: prios.get(i.number) ?? "normal" })));
    const criticalOpen = [...rows.started.map(([n]) => n), ...rows.ready, ...rows.relaunch.map(([n]) => n)].some((n) => prios.get(n) === "critical");
    const lowCap: LowCap = { cap: this.d.cfg.lowCap, running: activeByPrio.low, applied: criticalOpen };
    const isLow = (n: number) => prios.get(n) === "low";
    const sel = planLaunch({ ready, relaunch: rows.relaunch.map(([n]) => n), active, target: teff, batch: this.d.cfg.batch, low: { ...lowCap, isLow } });
    const relMap = new Map(rows.relaunch);
    const picks: Planned[] = [];
    const issueOf = new Map(snap.issues.map((i) => [i.number, i] as const));
    // Review-Only と stuck の上限は、どちらも新規着手 (picks) を空にする。数え方は VM 版 (launch_issues.py) と同じ。
    const pr = countOpenPrs(Object.values(this.s.prs).map((p) => ({ state: p.state, labels: p.labels ?? [] })));
    const prev = this.phase();
    const phase: PhaseState = { review_only: nextReviewOnly(prev.review_only, pr.openExclStuck), open_prs: pr.openExclStuck };
    phase.since = phase.review_only !== prev.review_only || !prev.since ? iso(nowMs) : prev.since;
    // launch を止める理由。stuck-ceiling (既存) を先に見る。rate-guard は REST の残量が 1,500 未満の間 (reconcile の読み取りは続く)。
    const stop = pr.stuck > this.d.cfg.stuckHigh ? "stuck-ceiling" : restGuardOn(this.meta.rest?.remaining) ? RATE_GUARD : undefined;
    // VM の状態を取り込むまでは launch しない (#2343)。取り込んだ launched の時刻は classify が recent に入れる。
    const blocked = this.d.cfg.importRequired && !this.meta.importedAt ? NO_IMPORT : undefined;
    const gated = phase.review_only || !!stop || !!blocked;
    const gateWhy = phase.review_only ? "review-only" : stop ?? blocked ?? "";
    const readyHeld = gated ? ready.map((r) => ({ n: r.n, why: gateWhy })) : sel.held.map((h) => ({ n: h.n, why: h.why }));
    for (const n of gated ? [] : sel.picks) {
      const i = issueOf.get(n);
      if (!i) continue;
      const base = this.s.pmArt[String(n)]?.line;
      const np = npPick.get(n);
      const dflt = defaultArtLine(base, i.artLine, i.title, i.labels);
      const cand = relMap.get(n) ?? np?.art ?? dflt;
      // 素材行は allowlist を通ったものだけを使う。通らなければ既定 (PM の行 → 本文の行 → 推定) に落とす。
      const art = validateArtLine(cand) ? cand : dflt;
      picks.push({ n, art, relaunch: relMap.has(n), np: np?.np, reportAt: np?.reportAt, ...(np?.recheck ? { recheck: true } : {}) });
    }
    const plan: Plan = {
      at: iso(nowMs),
      active,
      active_impl: act.impl,
      active_other: act.other,
      target: this.d.cfg.target,
      targetEff: teff,
      capEst,
      room: sel.room,
      picks,
      phase,
      open_prs_excl_stuck: pr.openExclStuck,
      stuck_prs: pr.stuck,
      stop,
      blocked,
      active_by_prio: activeByPrio,
      low_cap: lowCap,
      ready_held: readyHeld,
    };
    return { rows, plan, picks, unknown, children, stopBasis };
  }

  // ---------------------------------------------------------------- 実行
  // 同期が古い、または一覧を打ち切った (取りこぼしがあり得る) 間は false。launch と watchdog はこの間は書かない。
  private fresh(): boolean {
    return !!this.meta.fullSyncAt && !!this.meta.reconcileAt && this.d.now() - this.meta.reconcileAt < STALE_AFTER_MS && !this.meta.syncTruncated;
  }

  // open issue 数を 1 時間ごとに記録する。同期が古い間・一覧を打ち切った間は記録しない (誤った数を残さない)。
  private sampleOpen(now: number): void {
    if (!this.fresh()) return;
    const hist = this.d.store.get<OpenSample[]>("meta", "openHist") ?? [];
    const last = hist[hist.length - 1];
    if (last && now - last.at < OPEN_SAMPLE_MS) return;
    const open = Object.values(this.s.issues).filter((i) => i.state === "open").length;
    this.d.store.put("meta", "openHist", [...hist, { at: now, open }].slice(-OPEN_SAMPLE_MAX));
  }

  // Review-Only の状態は DO に保存する (未保存なら review_only: true)。
  private phase(): PhaseState {
    return this.d.store.get<PhaseState>("meta", "phase") ?? { review_only: true };
  }

  // 投稿した /oc の観測を進める (launchObs)。書くのは状態が変わったとき・観測した run の完了時刻が進んだときだけ。失敗の判定は同期が新しいときだけ。
  // dry-run は投稿しないので launchObs を作らず、ここでは何もしない。
  private observeLaunches(): void {
    const fresh = this.fresh();
    const now = this.d.now();
    const runs = Object.values(this.s.runs);
    for (const [k, obs] of this.d.store.all<LaunchObs>("launchObs")) {
      const title = this.s.issues[k]?.title;
      if (title === undefined) continue;
      const launchedMs = Date.parse(obs.at);
      const next = advanceLaunch(obs, now, observedBy(runs, title, launchedMs), fresh, doneAtOf(runs, title, launchedMs));
      if (!next) continue;
      this.d.store.put("launchObs", k, next);
      if (next.state !== obs.state) this.pushLog({ kind: next.state === "failed" ? "unobserved" : "observed", n: Number(k), note: next.state === "failed" ? "launch not observed in 5 min" : undefined });
    }
  }

  // launch を止めている条件 (haltReasons) の区間を進める。止まり続けている間は起点 (since) を残し、解消したら消す (#2795)。
  private updateHalt(plan: Plan): void {
    const reasons = haltReasons({ noImport: !!plan.blocked, stop: plan.stop, reviewOnly: plan.phase.review_only, stale: !this.fresh() });
    this.meta.halt = nextHalt(this.meta.halt, reasons, iso(this.d.now()));
  }

  async launch(gh: Gh | null): Promise<Plan> {
    this.observeLaunches();
    const { plan, picks, rows, unknown, children } = this.plan();
    this.meta.lastPlan = plan;
    this.meta.counters = this.meta.counters ?? this.zero();
    this.updateHalt(plan);
    if (!this.fresh()) {
      this.meta.lastError = { at: plan.at, what: "state not fresh: launch skipped" };
      this.saveMeta();
      return plan;
    }
    this.d.store.put("meta", "phase", plan.phase);
    // shadow 用の記録 (dry-run でも live でも、計画に載った issue を残す)。15 分の窓で突き合わせるので、2 窓分だけ保つ。
    const now = this.d.now();
    this.wouldRecs = [...this.wouldRecs.filter((w) => w.at >= now - 2 * SHADOW_WINDOW_MS), ...(picks.length ? [{ at: now, ns: picks.map((p) => p.n) }] : [])];
    this.d.store.put("meta", "wouldRecs", this.wouldRecs);
    // 遷移したときだけ記録する (毎 tick 書かない)。
    const guarded = restGuardOn(this.meta.rest?.remaining);
    if (guarded !== !!this.meta.rateGuardOn) {
      this.meta.rateGuardOn = guarded;
      this.pushLog({ kind: "skip", note: `${RATE_GUARD} ${guarded ? "on" : "off"} remaining=${this.meta.rest?.remaining ?? "?"}` });
    }
    const live = this.launchLive() && gh;
    const planned = this.d.store.get<Record<string, number>>("meta", "planned") ?? {};
    // 再投入の意図は picks より先に処理する。picks が先に投稿すると、同じ issue の意図は『投稿の後に出た意図』として focus なしで処理済みになるため。
    // 意図で扱った issue (投稿・dry-run の記録) は picks から外す。停止中 (review-only・stuck・rate-guard・取り込み前の no-import) は picks も空なので、意図も処理しない (処理済みにせず次の tick に回す)。
    // prio:low の枠 (LOW_CAP) は、意図の投稿と picks で共有する。意図が先に枠を使えば、picks の low はその分を除く。
    const lowGate = { left: lowAllowance(plan.low_cap) };
    // 1 tick の枠 = min(room, BATCH)。再投入の意図と ready の picks が共有する。relaunch の picks は枠を超えても出す (planLaunch と同じ)。
    const frame = { left: Math.min(plan.room, this.d.cfg.batch) };
    const intent = plan.phase.review_only || plan.stop || plan.blocked ? { halted: false, handled: new Set<number>() } : await this.relaunchIntents(gh, !!live, planned, { rows, unknown, children }, lowGate, frame);
    const prios = this.prioMap();
    for (const p of intent.halted ? [] : picks) {
      if (intent.handled.has(p.n)) continue;
      let body: string;
      try {
        body = buildLaunchBody(p.art, undefined, !!p.recheck);
      } catch {
        this.pushLog({ kind: "skip", n: p.n, note: "invalid artifacts line" });
        continue;
      }
      // relaunch は枠を超えても全件出す (planLaunch と同じ)。新規の picks は意図が残した枠の中だけ。
      if (!p.relaunch && frame.left <= 0) continue;
      if (prios.get(p.n) === "low") {
        if (lowGate.left <= 0) continue;
        lowGate.left--;
      }
      if (!live) {
        // dry-run: 同じ issue を RUN_WINDOW_H の間は再掲しない (計画の変化だけを残す)。投稿はしない。
        if (this.d.now() - (planned[String(p.n)] ?? 0) < RUN_WINDOW_H * 3_600_000) continue;
        planned[String(p.n)] = this.d.now();
        frame.left--;
        this.meta.counters.wouldLaunch++;
        this.pushLog({ kind: "would-launch", n: p.n, art: p.art, note: p.relaunch ? "relaunch" : undefined });
        continue;
      }
      // 投稿の応答で残量が下がるので、1 件ごとに見直す。
      if (restGuardOn(this.meta.rest?.remaining)) break;
      frame.left--;
      try {
        await gh!.comment(p.n, body);
      } catch (e) {
        this.pushLog({ kind: "error", n: p.n, note: e instanceof GhError ? e.message : "comment failed" });
        if (e instanceof GhError && (e.status === 403 || e.status === 429)) break;
        continue;
      }
      this.markPosted(p.n, iso(this.d.now()));
      if (p.relaunch) {
        const prev = this.d.store.get<{ count: number; art: string | null }>("relaunch", String(p.n)) ?? { count: 0, art: null };
        this.d.store.put("relaunch", String(p.n), { count: prev.count + 1, art: p.art });
      }
      // 計数は artifact・unknown・blocked の再投入 (stop・split は数えない)。blocked は再着手の根拠の報告の時刻を残す (同じ報告では再着手しない)。
      if (p.np) {
        const c = this.noPrState(p.n);
        this.d.store.put("relaunch", `np:${p.n}`, {
          ...c,
          count: c.count + 1,
          unknown: c.unknown + (p.np === "unknown" ? 1 : 0),
          artifact: c.artifact + (p.np === "artifact" ? 1 : 0),
          ...(p.np === "blocked" && p.reportAt ? { blocked: p.reportAt } : {}),
          art: p.art,
        });
      }
      this.meta.counters.launched++;
      this.pushLog({ kind: "launch", n: p.n, art: p.art });
    }
    this.d.store.put("meta", "planned", planned);
    this.saveMeta();
    return plan;
  }

  // /oc を投稿した issue の印: launchedAt・launchObs (投稿後の観測の起点)。oc:no-pr の計数は呼び出し側 (picks の np・再投入の意図) が行う。
  private markPosted(n: number, at: string): void {
    this.tickPosted++;
    this.d.store.put("launchedAt", String(n), at);
    this.s = { ...this.s, launchedAt: { ...this.s.launchedAt, [String(n)]: at } };
    this.d.store.put("launchObs", String(n), { state: "launched", at, changedAt: at } satisfies LaunchObs);
  }

  // 再投入の意図 (oc-pm-intent: relaunch)。checkRelaunchIntent の検査を全て通し、かつ分類 (plan の rows) で投稿してよい行だけ /oc を投稿する。
  // 投稿してよいのは ready・relaunch・stopped (PM の判断待ち)。user・hold・blocked・started は理由を counters.intentRejected に数えて処理済みにする。
  // recent (着手直後の待ち) は処理済みにせず、次の tick に回す。検査・分類で落ちた意図も、毎 tick 数え直さないように処理済みにする。
  // 戻り値: 403/429 や残量で止まったか (halted)、この tick で投稿 (dry-run は記録) の対象にした issue (handled。picks から外す)。
  // dry-run では投稿せず記録だけする。処理済みにはしないので、live に切り替えると投稿される (README の『PM agent の判断待ち』を参照)。
  private async relaunchIntents(
    gh: Gh | null,
    live: boolean,
    planned: Record<string, number>,
    ctx: { rows: Rows; unknown: Set<number>; children: Record<string, number[]> },
    lowGate: { left: number },
    frame: { left: number },
  ): Promise<{ halted: boolean; handled: Set<number> }> {
    const nowMs = this.d.now();
    // handled は picks から外す issue。枠 (frame) で待たせた意図の issue も入れる (picks が先に投稿すると、意図が focus なしで処理済みになるため)。
    const handled = new Set<number>();
    const prios = this.prioMap();
    const placed = new Map<number, { row: keyof Rows; why: string; openPr: boolean }>();
    for (const row of Object.keys(ctx.rows) as Array<keyof Rows>) {
      for (const x of ctx.rows[row] as unknown[]) {
        const n = Array.isArray(x) ? (x[0] as number) : (x as number);
        const why: unknown = Array.isArray(x) ? x[1] : undefined;
        // started の理由は PR#・run の一覧。open な PR が 1 つでもあれば拒否し、実行中の run だけなら待つ (intentGate)。
        placed.set(n, {
          row,
          why: typeof why === "string" ? why : "",
          openPr: Array.isArray(why) && why.some((w) => typeof w === "string" && w.startsWith("PR#")),
        });
      }
    }
    const c = (this.meta.counters ??= this.zero());
    for (const [k, sig] of Object.entries(this.s.sig)) {
      const r = sig.relaunch;
      const issue = this.s.issues[k];
      if (!r || !issue || issue.state !== "open") continue;
      const n = Number(k);
      const key = `it:${k}`;
      const st = this.d.store.get<{ seen?: string; posted?: number[] }>("relaunch", key) ?? {};
      const at = Date.parse(r.at);
      // 処理済みかは、いまの意図 (issue ごとの 1 枠) の識別子で比べる。時刻で比べると、先に処理した第三者の意図より後に届く bot の古い意図が捨てられる。
      const ident = `${relaunchAuthorOf(r)}:${r.id ?? r.at}`;
      // 旧表記 (bot:/user:) の処理済みは、同じ id (無ければ at) かつ書き手の区分が変わっていないときだけ処理済みとみなす。
      // 表記の移行で一括再計数しない (CI-242)。区分が修復で pm/impl に変わった意図は、再評価して解放する。
      const legacy = /^(bot|user):(.*)$/.exec(st.seen ?? "");
      const legacySeen = !!legacy && legacy[2] === String(r.id ?? r.at) && relaunchAuthorOf(r) === (legacy[1] === "bot" ? "impl" : "other");
      if (st.seen === ident || legacySeen) continue;
      // 最後の /oc より前に出た意図は捨てる (PM の手動の /oc を含む)。
      if ((Date.parse(this.s.launchedAt[k] ?? "") || 0) >= at) {
        this.d.store.put("relaunch", key, { ...st, seen: ident });
        continue;
      }
      const reject = (reason: string) => {
        c.intentRejected = { ...(c.intentRejected ?? {}), [reason]: (c.intentRejected?.[reason] ?? 0) + 1 };
        this.d.store.put("relaunch", key, { ...st, seen: ident });
        this.pushLog({ kind: "skip", n, note: `relaunch intent rejected: ${reason}` });
      };
      const v = checkRelaunchIntent(n, r, st.posted ?? [], nowMs);
      if (!v.ok) {
        reject(v.reason);
        continue;
      }
      const gate = this.intentGate(n, placed.get(n), ctx, nowMs, prios);
      if (gate.kind === "wait") continue;
      if (gate.kind === "reject") {
        reject(gate.reason);
        continue;
      }
      // 1 tick の枠 (picks と共有)。枠が尽きた意図は投稿せず、picks が bare の /oc を出さないように handled に入れる。処理済みにはしないので次の tick に回る。
      if (frame.left <= 0) {
        handled.add(n);
        continue;
      }
      // prio:low の上限に達していれば、処理済みにせず次の tick に回す (picks と同じ枠)。
      if (prios.get(n) === "low") {
        if (lowGate.left <= 0) continue;
        lowGate.left--;
      }
      handled.add(n);
      if (!live) {
        // dry-run: launch の計画と同じく、同じ issue は RUN_WINDOW_H の間は再掲しない。
        if (nowMs - (planned[key] ?? 0) < RUN_WINDOW_H * 3_600_000) continue;
        planned[key] = nowMs;
        frame.left--;
        c.intentWouldLaunch = (c.intentWouldLaunch ?? 0) + 1;
        this.pushLog({ kind: "would-launch", n, art: v.art, note: "relaunch intent" });
        continue;
      }
      if (restGuardOn(this.meta.rest?.remaining)) return { halted: true, handled };
      frame.left--;
      try {
        await gh!.comment(n, buildLaunchBody(v.art, v.focus));
      } catch (e) {
        this.pushLog({ kind: "error", n, note: e instanceof GhError ? e.message : "comment failed" });
        if (e instanceof GhError && (e.status === 403 || e.status === 429)) return { halted: true, handled };
        continue;
      }
      this.markPosted(n, iso(nowMs));
      // oc:no-pr への意図の投稿も、picks の再着手と同じ上限 (NO_PR_MAX_RELAUNCH) に数える。
      if ((issue.labels ?? []).includes("oc:no-pr")) {
        const np = this.noPrState(n);
        this.d.store.put("relaunch", `np:${n}`, { ...np, count: np.count + 1, art: v.art });
      }
      const posted = [...(st.posted ?? []), nowMs].filter((t) => nowMs - t < RELAUNCH_WINDOW_MS);
      this.d.store.put("relaunch", key, { seen: ident, posted });
      c.launched++;
      c.intentLaunched = (c.intentLaunched ?? 0) + 1;
      this.pushLog({ kind: "launch", n, art: v.art, note: "relaunch intent" });
    }
    return { halted: false, handled };
  }

  // 意図の投稿先の判定。wait は次の tick に回す (処理済みにしない)。reject は処理済みにして理由を数える。
  // 行は plan の rows (picks と同じ分類)。oc:stuck・pm-apply・needs-user-input・oc:hold と、oc:no-pr の cooldown・上限は picks の再着手と同じに見る。
  // 子 issue (open) を持つ親は、停止報告の内容に依らず投稿しない (plan は ready・relaunch の親を blocked・stopped に移すが、停止報告だけの親は stopped のまま残るため)。
  private intentGate(
    n: number,
    at: { row: keyof Rows; why: string; openPr: boolean } | undefined,
    ctx: { unknown: Set<number>; children: Record<string, number[]> },
    nowMs: number,
    prios: Map<number, Prio>,
  ): { kind: "post" } | { kind: "wait" } | { kind: "reject"; reason: string } {
    if (!at) return { kind: "wait" };
    // blocked_by が未同期 (unknown) の間は、ready でも blocked の行に移っているので、先に待つ (確定してから拒否・投稿を決める)。
    if (at.row === "recent" || ctx.unknown.has(n)) return { kind: "wait" };
    if (at.row === "user" || at.row === "hold" || at.row === "blocked") return { kind: "reject", reason: at.row };
    // 実行中の run だけで started のときは、run の完了後に分類し直すまで待つ (run の途中で意図を受け取っても捨てない)。open な PR があれば拒否する。
    if (at.row === "started") return at.openPr ? { kind: "reject", reason: "started" } : { kind: "wait" };
    const labels = this.s.issues[String(n)]?.labels ?? [];
    if (labels.includes("oc:stuck") || HOLD_LABELS.some((l) => labels.includes(l))) return { kind: "reject", reason: "user" };
    if ((ctx.children[String(n)] ?? []).length) return { kind: "reject", reason: "stopped" };
    if (labels.includes("oc:no-pr")) {
      if (nowMs - this.lastAct(n) < noPrCooldownMs(prios.get(n) ?? "normal", this.d.cfg.noPrCooldownH)) return { kind: "wait" };
      if (this.noPrState(n).count >= NO_PR_MAX_RELAUNCH) return { kind: "reject", reason: "stopped" };
    }
    if (at.row === "stopped" && INTENT_HARD_STOP.includes(at.why)) return { kind: "reject", reason: "stopped" };
    return { kind: "post" };
  }

  // oc:no-pr の cooldown の起点: /oc の投稿か bot のコメントの遅い方 (ms)。
  private lastAct(n: number): number {
    return Math.max(Date.parse(this.s.launchedAt[String(n)] ?? "") || 0, Date.parse(this.s.botLast[String(n)]?.at ?? "") || 0);
  }

  // 区分の実効値 (launch・LOW_CAP・no-pr の cooldown・/status で同じ値を使う)。親からの継承を含む (#3973)。
  // closed の親も状態で判定するため、snapshot (open だけ) ではなく s.issues 全体から作る。
  private prioMap(): Map<number, Prio> {
    return effectivePrioMap(prioIssues(this.s));
  }

  async watchdog(gh: Gh | null): Promise<"dispatched" | "would" | "skipped"> {
    const minGap = Math.max(0, this.d.cfg.watchdogIntervalS * 1000 - WATCHDOG_JITTER_MS);
    const last = this.meta.watchdogAt ?? 0;
    // cron と alarm の両方が毎分呼ぶ。前回の送信 (dry-run では記録) から周期が過ぎるまでは送らない。送信に失敗したときは記録しないので次の tick で再試行する。
    if (this.d.now() - last < minGap) return "skipped";
    if (!this.fresh()) return "skipped";
    this.meta.counters = this.meta.counters ?? this.zero();
    if (!this.dispatchLive() || !gh) {
      this.meta.watchdogAt = this.d.now();
      this.meta.counters.wouldDispatch++;
      this.saveMeta();
      this.pushLog({ kind: "would-dispatch", note: "oc-watchdog" });
      return "would";
    }
    try {
      await gh.dispatch("oc-watchdog");
    } catch (e) {
      this.pushLog({ kind: "error", note: e instanceof GhError ? e.message : "dispatch failed" });
      return "skipped";
    }
    this.meta.watchdogAt = this.meta.lastDispatchAt = this.d.now();
    this.meta.counters.dispatched++;
    this.saveMeta();
    this.pushLog({ kind: "dispatch", note: "oc-watchdog" });
    return "dispatched";
  }

  // ---------------------------------------------------------------- oc-pm
  // PM の判断が要る終端状態を決定的に検出する (本文は解析しない)。
  detectPmTargets(): PmTarget[] {
    return detectPm(this.s, {
      bots: this.d.cfg.pmTargetBots,
      nowMs: this.d.now(),
      npCount: (n) => this.d.store.get<{ count: number }>("relaunch", `np:${n}`)?.count ?? 0,
      // 新しい素材の無い artifact は、unknown の枠 (再投入 1 回) を使い切るか、再投入の上限に達したら oc-pm に回す (#3185)。
      artSpent: (n) => this.artExtra(n) === null && (this.noPrState(n).unknown >= 1 || this.noPrState(n).count >= NO_PR_MAX_RELAUNCH),
    });
  }

  // 履歴は live と dry-run で分ける (dry-run の記録が、live に切り替えた直後の送信を抑止しないように)。
  private pmHistoryKey(): string {
    return this.dispatchLive() ? "pmDispatch" : "pmWould";
  }
  private pmHistory(): HistoryEntry[] {
    return pruneHistory(this.d.now(), this.d.store.get<HistoryEntry[]>("meta", this.pmHistoryKey()) ?? []);
  }
  // 毎時上限で見送った件数 (#3462)。履歴と同じく live / dry-run で分ける。
  private pmHourSkipKey(): string {
    return this.dispatchLive() ? "pmHourSkipLive" : "pmHourSkipWould";
  }
  private pmHourSkips(now: number): SkipEntry[] {
    return pruneHistory(now, this.d.store.get<SkipEntry[]>("meta", this.pmHourSkipKey()) ?? []);
  }
  private recordHourSkip(now: number, n: number): void {
    if (n <= 0) return;
    this.d.store.put("meta", this.pmHourSkipKey(), [...this.pmHourSkips(now), { at: now, n }]);
  }
  private pmDispatch1hByKind(now: number): Record<string, number> {
    const out: Record<string, number> = Object.fromEntries(DETECTED_KINDS.map((k) => [k, 0]));
    for (const h of this.pmHistory()) if (now - h.at < 3_600_000) out[h.kind] = (out[h.kind] ?? 0) + 1;
    return out;
  }

  // 停止行の直接の再投入 (wake・CI-250)。停止行のうち oldest-first の対象へ、/oc の再投入コメントを Worker が直接投稿する (oc-pm の判断を挟まない)。
  // 投稿の条件は launch と同じ: 停止中 (stop・blocked・review-only) では送らず、同期が古いときも送らない。LIVE_LAUNCH=1 のときだけ投稿し、dry-run は記録する。
  // 稼働枠: plan.room (TARGET − active) から、この tick で launch・意図が使った分を引いた残りまで。残りが無ければ送らない (TARGET を超えない)。
  // 1 時間に WAKE_PER_H 件・同じ issue は 24 時間に WAKE_REF_DAY_MAX 件。prio:critical・needs-user-input は除く (selectWake)。
  // 対象は直前の報告が『## 停止報告』の見出しを持つ停止行だけ (承認の『明確な停止報告』。報告本文 botReport で判定)。
  // 投稿した停止行は同じ tick の oc-pm に送らない (run が進行中になるため)。
  private wakeHistory(now: number, key: "wakeLive" | "wakeWould"): Array<{ ref: number; at: number }> {
    return pruneHistory(now, this.d.store.get<Array<{ ref: number; at: number }>>("meta", key) ?? []);
  }
  async wakeStopped(gh: Gh | null): Promise<PmTarget[]> {
    const plan = this.meta.lastPlan;
    if (!this.fresh() || !plan || plan.stop || plan.blocked || plan.phase.review_only) return [];
    const frame = plan.room - this.tickPosted;
    if (frame <= 0) return [];
    const live = !!(this.launchLive() && gh);
    const now = this.d.now();
    const key = live ? "wakeLive" : "wakeWould";
    const hist = this.wakeHistory(now, key);
    const targets = this.detectPmTargets().filter((tg) => tg.kind === "stopped_report" && isStopReport(this.s.botReport[String(tg.ref)]?.body ?? ""));
    const picks = selectWake(now, targets, hist, {
      perH: this.d.cfg.wakePerH,
      refDayMax: this.d.cfg.wakeRefDayMax,
      excludeLabels: ["needs-user-input"],
      labelsOf: (n) => this.s.issues[String(n)]?.labels ?? [],
    }).slice(0, frame);
    if (picks.length === 0) return [];
    this.meta.counters = this.meta.counters ?? this.zero();
    const sent: PmTarget[] = [];
    for (const tg of picks) {
      const i = this.s.issues[String(tg.ref)];
      const art = defaultArtLine(this.s.pmArt[String(tg.ref)]?.line, i?.artLine, i?.title ?? "", i?.labels ?? []);
      if (!live) {
        hist.push({ ref: tg.ref, at: now });
        this.meta.counters.wouldWake = (this.meta.counters.wouldWake ?? 0) + 1;
        this.pushLog({ kind: "would-wake", n: tg.ref, art, note: "stopped_report" });
        sent.push(tg);
        continue;
      }
      if (restGuardOn(this.meta.rest?.remaining)) break;
      // 失敗した試行も履歴に数える (毎分叩き直さない。上限はそのまま効く)。
      hist.push({ ref: tg.ref, at: now });
      try {
        await gh!.comment(tg.ref, buildLaunchBody(art));
      } catch (e) {
        this.pushLog({ kind: "error", n: tg.ref, note: e instanceof GhError ? `wake: ${e.message}` : "wake failed" });
        if (e instanceof GhError && (e.status === 403 || e.status === 429)) break;
        continue;
      }
      this.markPosted(tg.ref, iso(now));
      this.meta.counters.wakeSent = (this.meta.counters.wakeSent ?? 0) + 1;
      this.pushLog({ kind: "wake", n: tg.ref, art, note: "stopped_report" });
      sent.push(tg);
    }
    this.d.store.put("meta", key, hist);
    this.saveMeta();
    return sent;
  }

  // 検出した対象を oc-pm で送る。payload は kind (列挙) と ref (数字) だけ。LIVE_DISPATCH=1 のときだけ送る (oc-watchdog と同じスイッチ)。
  // 同期が古い間は送らない (誤った対象を起こさない)。
  async pmDispatch(gh: Gh | null): Promise<{ sent: PmTarget[]; would: PmTarget[] }> {
    const out = { sent: [] as PmTarget[], would: [] as PmTarget[] };
    if (!this.fresh()) return out;
    const live = !!(this.dispatchLive() && gh);
    const now = this.d.now();
    const hist = this.pmHistory();
    const { send, skipped } = selectDispatch(now, this.detectPmTargets(), hist, { stoppedPerHour: this.d.cfg.stoppedIntakePerH });
    this.meta.counters = this.meta.counters ?? this.zero();
    for (const tg of send) {
      if (!validPayload(tg.kind, tg.ref)) continue;
      if (!live) {
        hist.push({ kind: tg.kind, ref: tg.ref, at: now, prio: tg.prio });
        this.meta.counters.wouldDispatchPm = (this.meta.counters.wouldDispatchPm ?? 0) + 1;
        this.pushLog({ kind: "would-pm-dispatch", n: tg.ref, note: tg.kind });
        out.would.push(tg);
        continue;
      }
      // 失敗した試行も履歴に数える (同じ対象を毎分叩かない。上限はそのまま効く)
      hist.push({ kind: tg.kind, ref: tg.ref, at: now, prio: tg.prio });
      try {
        await gh!.dispatchPm(tg.kind, tg.ref);
      } catch (e) {
        this.pushLog({ kind: "error", n: tg.ref, note: e instanceof GhError ? `oc-pm ${tg.kind}: ${e.message}` : `oc-pm ${tg.kind}: dispatch failed` });
        if (e instanceof GhError && (e.status === 403 || e.status === 429)) break;
        continue;
      }
      this.meta.counters.pmDispatched = (this.meta.counters.pmDispatched ?? 0) + 1;
      this.pushLog({ kind: "pm-dispatch", n: tg.ref, note: tg.kind });
      out.sent.push(tg);
    }
    if (send.length > 0) {
      this.d.store.put("meta", this.pmHistoryKey(), hist);
      this.saveMeta();
    }
    // 毎時の枠による見送り。reserve は他の kind の最低配分 (KIND_MIN_PER_HOUR) のために枠を残した見送り (#3704)。
    this.recordHourSkip(now, skipped.filter((s) => s.why === "hour" || s.why === "reserve").length);
    return out;
  }

  // ---------------------------------------------------------------- 自動 close (規則 A)
  // merged PR を持つ親 issue を閉じる (判定は autoclose.ts の detectRuleA)。LIVE_CLOSE="1" のときだけ書く。既定は記録のみ (counters.wouldClose)。
  // 1 tick に最大 AUTO_CLOSE_MAX 件。同じ issue は書き込みの試行から 24 時間は再試行しない (閉じた後の配送遅延で二重にコメントしない)。
  // 同期が古い間は閉じない (一覧の取りこぼしで、参照の無いものを閉じないため)。
  async autoClose(gh: Gh | null): Promise<{ closed: CloseTarget[]; would: CloseTarget[] }> {
    const out = { closed: [] as CloseTarget[], would: [] as CloseTarget[] };
    if (!this.fresh()) return out;
    const live = !!(this.d.cfg.liveClose && gh);
    const now = this.d.now();
    const key = live ? "autoClose" : "autoCloseWould";
    const hold = live ? AUTO_CLOSE_RETRY_MS : AUTO_CLOSE_WOULD_MS;
    const seen: Record<string, number> = {};
    for (const [k, at] of Object.entries(this.d.store.get<Record<string, number>>("meta", key) ?? {})) if (now - at < hold) seen[k] = at;
    const picks = detectRuleA(this.s)
      .filter((t) => !(String(t.n) in seen))
      .slice(0, AUTO_CLOSE_MAX);
    if (picks.length === 0) return out;
    this.meta.counters = this.meta.counters ?? this.zero();
    for (const t of picks) {
      if (!live) {
        seen[String(t.n)] = now;
        this.meta.counters.wouldClose = (this.meta.counters.wouldClose ?? 0) + 1;
        this.pushLog({ kind: "would-close", n: t.n, note: `rule A merged #${t.mergedPr} child #${t.child}` });
        out.would.push(t);
        continue;
      }
      // レート制限の守りに当たったら、まだ試していない候補は記録しない (次の tick で改めて試す)。
      if (restGuardOn(this.meta.rest?.remaining)) break;
      seen[String(t.n)] = now;
      try {
        await gh!.comment(t.n, closeComment(t));
        await gh!.closeIssue(t.n);
      } catch (e) {
        this.pushLog({ kind: "error", n: t.n, note: e instanceof GhError ? `auto-close: ${e.message}` : "auto-close failed" });
        if (e instanceof GhError && (e.status === 403 || e.status === 429)) break;
        continue;
      }
      const cur = this.s.issues[String(t.n)];
      if (cur) {
        const next: IssueState = { ...cur, state: "closed", labels: [], body: "", updatedAt: iso(now) };
        this.d.store.put("issues", String(t.n), next);
        this.s = { ...this.s, issues: { ...this.s.issues, [String(t.n)]: next } };
      }
      this.meta.counters.closed = (this.meta.counters.closed ?? 0) + 1;
      this.pushLog({ kind: "close", n: t.n, note: `rule A merged #${t.mergedPr}` });
      out.closed.push(t);
    }
    this.d.store.put("meta", key, seen);
    this.saveMeta();
    return out;
  }

  // 日次のダイジェスト (oc-pm kind=digest ref=0)。時刻だけで送り、集計は PM agent が pm.md の digest 節で行う。
  // 初回の tick は起点を置くだけ (初めて動いた直後に起こさない)。以後 24 時間に 1 回。送信に失敗した試行も 1 回と数え、毎分叩き直さない。
  // 対象を指さないので、同期の新旧は問わない。
  async digest(gh: Gh | null): Promise<"sent" | "would" | "skipped"> {
    const now = this.d.now();
    if (this.meta.digestAt === undefined) {
      this.meta.digestAt = now;
      return "skipped";
    }
    if (now - this.meta.digestAt < DIGEST_EVERY_MS) return "skipped";
    this.meta.digestAt = now;
    this.meta.counters = this.meta.counters ?? this.zero();
    const hist = [...this.pmHistory(), { kind: DIGEST_KIND, ref: DIGEST_REF, at: now }];
    if (!this.dispatchLive() || !gh) {
      this.meta.counters.wouldDispatchPm = (this.meta.counters.wouldDispatchPm ?? 0) + 1;
      this.d.store.put("meta", this.pmHistoryKey(), hist);
      this.pushLog({ kind: "would-pm-dispatch", n: DIGEST_REF, note: DIGEST_KIND });
      this.saveMeta();
      return "would";
    }
    let sent = true;
    try {
      await gh.dispatchPm(DIGEST_KIND, DIGEST_REF);
    } catch (e) {
      sent = false;
      this.pushLog({ kind: "error", note: e instanceof GhError ? `oc-pm ${DIGEST_KIND}: ${e.message}` : `oc-pm ${DIGEST_KIND}: dispatch failed` });
    }
    this.d.store.put("meta", this.pmHistoryKey(), hist);
    if (sent) {
      this.meta.counters.pmDispatched = (this.meta.counters.pmDispatched ?? 0) + 1;
      this.pushLog({ kind: "pm-dispatch", n: DIGEST_REF, note: DIGEST_KIND });
    }
    this.saveMeta();
    return sent ? "sent" : "skipped";
  }

  // launch の停止が 30 分続いたら、PM agent に 1 回だけ知らせる (#2795)。新しい kind は作らず、digest (ref 0) を送る。
  // 同じ停止区間では 1 回だけ (失敗した試行も数える)。上限は pmHistory (同じ digest#0 は 60 分に 1 回、全体は 1 時間に 72 件) に従う。
  // 同期が古いときも送る (止まったまま古くなる場合こそ知らせる必要があるため)。LIVE_DISPATCH のときだけ送り、dry-run は would に記録する。
  // 降格中 (dispatch を止めている間) は送らず、区間の 1 回も使わずに保留する。解除の後に送る。
  async haltNotify(gh: Gh | null): Promise<"sent" | "would" | "skipped"> {
    const now = this.d.now();
    const halt = this.meta.halt;
    if (!halt || !haltNotifyDue(halt, now)) return "skipped";
    const hist = this.pmHistory();
    const within = (ms: number) => hist.filter((h) => now - h.at < ms);
    if (within(PM_LIMITS.dupMs).some((h) => h.kind === DIGEST_KIND && h.ref === DIGEST_REF)) return "skipped";
    if (within(PM_LIMITS.hourMs).length >= PM_LIMITS.hourMax) {
      this.recordHourSkip(now, 1);
      return "skipped";
    }
    const reason = halt.reasons[0] ?? "";
    const live = this.dispatchLive() && !!gh;
    const held = this.d.cfg.liveDispatch && !this.dispatchLive();
    if (!held) this.meta.halt = { ...halt, notifiedAt: iso(now) };
    this.meta.counters = this.meta.counters ?? this.zero();
    hist.push({ kind: DIGEST_KIND, ref: DIGEST_REF, at: now });
    if (!live) {
      this.meta.counters.wouldDispatchPm = (this.meta.counters.wouldDispatchPm ?? 0) + 1;
      this.d.store.put("meta", this.pmHistoryKey(), hist);
      this.pushLog({ kind: "would-pm-dispatch", n: DIGEST_REF, note: `launch-halt ${reason}` });
      this.saveMeta();
      return "would";
    }
    let sent = true;
    try {
      await gh.dispatchPm(DIGEST_KIND, DIGEST_REF);
    } catch (e) {
      sent = false;
      this.pushLog({ kind: "error", note: e instanceof GhError ? `oc-pm ${DIGEST_KIND} (launch-halt): ${e.message}` : `oc-pm ${DIGEST_KIND} (launch-halt): dispatch failed` });
    }
    this.d.store.put("meta", this.pmHistoryKey(), hist);
    if (sent) {
      this.meta.counters.pmDispatched = (this.meta.counters.pmDispatched ?? 0) + 1;
      this.pushLog({ kind: "pm-dispatch", n: DIGEST_REF, note: `launch-halt ${reason}` });
    }
    this.saveMeta();
    return sent ? "sent" : "skipped";
  }

  // 失敗した webhook 配送の回収 (#2339)。GitHub は失敗した配送を自動で再送しないので、App の配送一覧 (JWT) から
  // status != OK のものを古い順に選ぶ。同じ guid に OK の配送が 1 つでもあれば回収済みとみなす。
  // POST は LIVE_REDELIVER=1 かつ rate-guard が無いときだけ。dry-run は guid ごとに 1 回だけ数える (counters.wouldRedeliver)。
  async redeliver(app: Gh | null): Promise<void> {
    const now = this.d.now();
    if (!app || now - (this.meta.redeliverAt ?? 0) < REDELIVER_EVERY_MS) return;
    this.meta.redeliverAt = now;
    this.meta.counters = this.meta.counters ?? this.zero();
    let list: unknown;
    try {
      list = (await app.req<unknown>("GET", "/app/hook/deliveries?per_page=100")).json;
    } catch (e) {
      this.pushLog({ kind: "error", note: e instanceof GhError ? `hook deliveries: ${e.message}` : "hook deliveries failed" });
      this.saveMeta();
      return;
    }
    const all: any[] = Array.isArray(list) ? list.filter((d) => !!d && typeof d === "object") : [];
    const okGuids = new Set(all.filter((d) => d.status === "OK").map((d) => String(d.guid ?? d.id)));
    // 同じ guid は 1 回だけ扱う。古い順 (一覧は新しい順)。再送された配送 (redelivery) は再送しない: 再送の失敗を再送すると連鎖し、
    // guid が変わる実装では guid の上限で止まらないため。元の配送 (redelivery=false) の上限 (3 回) だけで止める。
    const byGuid = new Map<string, any>();
    for (const d of [...all].reverse()) {
      if (d.status === "OK" || d.redelivery === true || !Number.isInteger(d.id)) continue;
      const guid = String(d.guid ?? d.id);
      if (okGuids.has(guid) || byGuid.has(guid)) continue;
      byGuid.set(guid, d);
    }
    const book = this.meta.redeliver ?? {};
    const keep: Record<string, { n: number; at: number }> = {};
    for (const guid of byGuid.keys()) keep[guid] = book[guid] ?? { n: 0, at: now };
    const live = this.d.cfg.liveRedeliver && !restGuardOn(this.meta.rest?.remaining);
    // 試行の少ないものから送る (同じ回数の中では古い順。安定ソート)。古いものの再試行で、新しい失敗が上限の外に押し出されないように。
    const order = [...byGuid.entries()].sort((a, b) => keep[a[0]].n - keep[b[0]].n);
    let sent = 0;
    for (const [guid, d] of order) {
      const prev = keep[guid];
      if (prev.n >= REDELIVER_MAX_PER_GUID) continue;
      if (!live) {
        if (book[guid] === undefined) {
          this.meta.counters.wouldRedeliver = (this.meta.counters.wouldRedeliver ?? 0) + 1;
          this.pushLog({ kind: "would-redeliver", note: `delivery ${d.id}` });
        }
        continue;
      }
      if (sent >= REDELIVER_MAX_PER_SCAN) continue;
      sent++;
      // 失敗した試行も数える (同じ配送を毎分叩かない。上限はそのまま効く)。
      keep[guid] = { n: prev.n + 1, at: now };
      try {
        await app.req("POST", `/app/hook/deliveries/${d.id}/attempts`);
      } catch (e) {
        this.pushLog({ kind: "error", note: e instanceof GhError ? `redeliver ${d.id}: ${e.message}` : `redeliver ${d.id} failed` });
        if (e instanceof GhError && (e.status === 403 || e.status === 429)) break;
        continue;
      }
      this.meta.counters.redelivered = (this.meta.counters.redelivered ?? 0) + 1;
      this.pushLog({ kind: "redeliver", note: `delivery ${d.id} attempt ${prev.n + 1}` });
    }
    this.meta.redeliver = keep;
    this.meta.redeliverFailed = all.filter((d) => d.status !== "OK").length;
    this.saveMeta();
  }

  // 1 回の点検。alarm (毎分・webhook 後 2 秒) と cron (毎分) の両方から呼ばれる。
  async tick(): Promise<{ ready: boolean }> {
    // cron と alarm が重なっても、同時に 2 回は走らせない (二重投稿の防止)。
    if (this.busy) return { ready: true };
    this.busy = true;
    try {
      return await this.tickInner();
    } finally {
      this.busy = false;
    }
  }

  private async tickInner(): Promise<{ ready: boolean }> {
    const now = this.d.now();
    this.meta.tickAt = now;
    this.dirty = false;
    this.tickPosted = 0;
    this.autoLiftStaleDemote();
    let gh: Gh | null = null;
    try {
      gh = await this.d.gh();
    } catch (e) {
      this.setError(now, e instanceof GhError ? e.message : "auth failed");
    }
    if (!gh) {
      this.saveMeta();
      return { ready: false };
    }
    try {
      // 保存値の版が古いときは、周期 (6 時間) を待たずに全体同期で補完する。失敗しても SIGNAL_RETRY_MS ごとにしか再試行しない (REST の枠を使い切らないため)。
      const stale = this.meta.signalVer !== SIGNAL_VER && now - (this.meta.signalTryAt ?? 0) >= SIGNAL_RETRY_MS;
      if (stale) this.meta.signalTryAt = now;
      if (!this.meta.fullSyncAt || now - this.meta.fullSyncAt > FULL_SYNC_EVERY_MS || stale) await this.fullSync(gh);
      else if (now - (this.meta.reconcileAt ?? 0) >= this.d.cfg.reconcileIntervalS * 1000) await this.reconcile(gh);
      // 同期が古い・打ち切り中は run 一覧が不完全なので観測しない (launch と同じ条件)。偽の飽和を作らないため。
      if (this.fresh()) {
        this.observe(now);
        this.rateAlert();
      }
      await this.watchdog(gh);
      await this.launch(gh);
      await this.haltNotify(gh);
      await this.wakeStopped(gh);
      await this.pmDispatch(gh);
      await this.autoClose(gh);
      await this.digest(gh);
      // 配送の回収は launch と独立に行い、失敗しても他の処理と lastError を止めない。
      try {
        await this.redeliver(this.d.app ? await this.d.app() : null);
      } catch {
        this.pushLog({ kind: "error", note: "hook redeliver failed" });
      }
      this.meta.lastError = undefined;
    } catch (e) {
      this.setError(now, e instanceof GhError ? e.message : "tick failed");
      this.pushLog({ kind: "error", note: this.meta.lastError?.what });
    }
    this.sampleOpen(now);
    this.logMetrics(now);
    this.saveMeta();
    return { ready: true };
  }

  // Custom Dashboard 用の観測ログ (CI-229)。tick の 1 回につき 1 行。観測の失敗で tick を止めない。
  private logMetrics(now: number): void {
    try {
      const row = metricsRow(this.status(), iso(now), !!this.meta.demoted, restGuardOn(this.meta.rest?.remaining));
      console.log(this.clean(JSON.stringify(row)));
      this.writeAe(row);
    } catch {
      // 観測ログは付随の出力。失敗しても launch・dispatch の判定は続ける。
    }
  }

  // AE へ 1 データポイント (CI-230)。書けなくても tick は止めない (書き込みの失敗は握る)。
  private writeAe(row: Record<string, unknown>): void {
    if (!this.d.ae) return;
    try {
      this.d.ae.writeDataPoint(aePoint(row));
    } catch {
      // 観測の書き込みは付随。失敗しても判定は続ける。
    }
  }

  // 次の alarm までの待ち (ms)。dirty (webhook 直後) は 2 秒、それ以外は 60 秒。
  nextDelayMs(): number {
    return this.dirty ? 2000 : 60_000;
  }

  // 率制限の判定 (#2345・CI-66)。直近 30 分に完了した opencode.yaml の run のうち、cause=rate_limit のマーカーがあるものを数える。
  // 件数と割合の条件を RATE_STREAK 回連続で満たしたら alert。alert は通知しない (起票は CI-67)。REST は呼ばない。
  // 評価は tick ごとだが、alarm と cron が重なった分は数えない (RATE_EVAL_GAP_MS 以内は評価しない)。
  rateAlert(): void {
    const now = this.d.now();
    const prev = this.meta.rateAlert;
    if (prev && now - prev.at < RATE_EVAL_GAP_MS) return;
    let count = 0;
    let total = 0;
    for (const r of Object.values(this.s.runs)) {
      if (r.status !== "completed" || !isOpencodeRun(r)) continue;
      const t = Date.parse(r.updatedAt);
      if (!(t > now - RATE_WINDOW_MS && t <= now)) continue;
      total++;
      if (this.s.rateRuns[String(r.id)]) count++;
    }
    const streak = rateHit(count, total) ? (prev && now - prev.at <= RATE_EVAL_MAX_GAP_MS ? prev.streak : 0) + 1 : 0;
    const alert = streak >= RATE_STREAK;
    if (alert !== (prev?.alert ?? false)) this.pushLog({ kind: "rate-alert", note: alert ? "on" : "off" });
    this.meta.rateAlert = { at: now, count, total, streak, alert };
  }

  // ---------------------------------------------------------------- 観測
  private launchUnobserved(): number[] {
    return this.d.store
      .all<LaunchObs>("launchObs")
      .filter(([, v]) => v.state === "failed")
      .map(([k]) => Number(k))
      .sort((a, b) => a - b);
  }

  // 集計だけを返す (本文・タイトルは含めない。issue 番号は公開 repo の情報)。
  status(extra: Record<string, unknown> = {}): Record<string, unknown> {
    const { rows, plan, stopBasis } = this.plan();
    const c = (k: keyof Rows) => rows[k].length;
    const open = Object.values(this.s.issues).filter((i) => i.state === "open").length;
    const detected = this.detectPmTargets();
    // critical は prio:critical の対象の件数 (kind の内訳と重なる。kind の合計とは一致しない)。
    const pmDetected: Record<string, number> = { ...Object.fromEntries(DETECTED_KINDS.map((k) => [k, 0])), critical: 0 };
    for (const d of detected) {
      pmDetected[d.kind]++;
      if (d.prio === "critical") pmDetected.critical++;
    }
    // 稼働中の run を状態別に数える (event も workflow も問わない。TARGET に数える active_runs とは別の集計)。
    const running = { in_progress: 0, queued: 0, pending: 0 };
    for (const r of Object.values(this.s.runs)) {
      if (r.status === "in_progress") running.in_progress++;
      else if (r.status === "queued") running.queued++;
      else if (r.status === "pending") running.pending++;
    }
    const now = this.d.now();
    const cnt = this.runCounts(now);
    // 既存の counters に無いキー (#2339 の redelivered・wouldRedeliver など) は 0 として出す。
    const counters = { ...this.zero(), ...(this.meta.counters ?? {}) };
    const rest = this.meta.rest;
    const lastError = this.meta.lastError ? { ...this.meta.lastError, what: this.clean(this.meta.lastError.what) } : null;
    // 自律運転の指標。件数と時間だけで、題名・本文・login は出さない (issue / PR 番号は可)。
    const openIssues = Object.values(this.s.issues).filter((i) => i.state === "open");
    const openPrs = Object.values(this.s.prs).filter((p) => p.state === "open");
    const withLabel = (l: string) => (x: { labels?: string[] }) => (x.labels ?? []).includes(l);
    const stuckAges = openPrs
      .filter(withLabel(STUCK_LABEL))
      .map((p) => Math.max(0, Math.floor((now - Date.parse(this.s.sig[String(p.number)]?.stop?.at ?? p.updatedAt)) / 60_000)));
    // 着手待ち (ready) を優先の区分で数える (launch は critical を先頭、low を末尾に並べる)。
    const readyByPrio = { critical: 0, normal: 0, low: 0 };
    const prios = this.prioMap();
    for (const n of rows.ready) readyByPrio[prios.get(n) ?? "normal"]++;
    // oc-pm の直近 1 時間の送信を区分別に数える (pm_dispatch_1h と同じ窓・同じ履歴。prio の無い古い履歴は normal)。
    const pmByPrio: Record<Prio, number> = { critical: 0, normal: 0, low: 0 };
    for (const h of this.pmHistory()) if (now - h.at < 3_600_000) pmByPrio[h.prio ?? "normal"]++;
    const noPrByReason = { split: 0, artifact: 0, unknown: 0, blocked: 0, stop: 0 };
    for (const i of openIssues.filter(withLabel(NO_PR_LABEL))) {
      const r = this.s.sig[String(i.number)]?.outcome?.reason;
      if (r && r in noPrByReason) noPrByReason[r as keyof typeof noPrByReason]++;
    }
    const countLabel = (l: string) => openIssues.filter(withLabel(l)).length + openPrs.filter(withLabel(l)).length;
    const mergedDay = Object.values(this.s.prs).filter((p) => {
      const t = p.mergedAt ? Date.parse(p.mergedAt) : NaN;
      return p.merged && t > now - DAY_MS && t <= now;
    });
    const refsOnly = mergedDay.filter((p) => p.refsOnly === true).length;
    // 24 時間前以前の点のうち最も新しいもの。無ければ (履歴が 24 時間分に満たない) null。
    let base: OpenSample | undefined;
    for (const h of this.d.store.get<OpenSample[]>("meta", "openHist") ?? []) if (h.at <= now - DAY_MS && (!base || h.at > base.at)) base = h;
    // launch を止めている条件 (#2795)。止めていなければ launch_halted は null。since は保存した区間の起点 (無ければ今)。
    const haltedReasons = haltReasons({ noImport: !!plan.blocked, stop: plan.stop, reviewOnly: plan.phase.review_only, stale: !this.fresh() });
    const haltedSince = haltedReasons.length ? (this.meta.halt?.since ?? iso(now)) : undefined;
    // 保留中の issue ごとの理由と解除見込み (#5110)。行は plan の rows をそのまま見る。着手判断には使わない。
    const doneAtOfIssue = new Map<number, string>();
    for (const [k, v] of this.d.store.all<LaunchObs>("launchObs")) if (v.state === "observed" && v.doneAt !== undefined) doneAtOfIssue.set(Number(k), v.doneAt);
    const holds: Hold[] = [
      ...rows.recent.map(([n, note]) => recentHold(n, note, {
        botAt: Date.parse(this.s.botLast[String(n)]?.at ?? "") || undefined,
        launchedAt: Date.parse(this.s.launchedAt[String(n)] ?? "") || undefined,
        doneAt: Date.parse(doneAtOfIssue.get(n) ?? "") || undefined,
        lastAct: this.lastAct(n) || undefined,
        cooldownMs: noPrCooldownMs(prios.get(n) ?? "normal", this.d.cfg.noPrCooldownH),
      })),
      ...rows.stopped.map(([n, note]) => stoppedHold(n, note, stopBasis.get(n))),
      ...plan.ready_held.map((h) => readyHold(h.n, h.why, { restReset: this.meta.rest?.reset })),
    ];
    return {
      // デプロイした commit (--var BUILD_COMMIT)。渡していなければ null。反映の確認に使う (README『再デプロイ』手順 5)。
      build: this.d.cfg.build,
      // 止まっている理由 (先頭が主な理由) と止まり始めた時刻。15 分以上止まり、着手待ち (ready) と空き枠 (room) がある間は launch_halted_overdue が true。
      launch_halted: haltedSince ? { reason: haltedReasons[0], since: haltedSince } : null,
      launch_halted_overdue: haltOverdue(haltedSince, now, c("ready"), plan.room),
      // 着手待ちでない issue (recent・stopped) の理由と解除見込み (#5110)。until は時間の窓で解ける見込み (ISO)。null は時間では解けない (PM・人の判断待ち・観測待ち)。
      launch_holds: holds,
      // mode は両方の経路が live のときだけ "live" (pm_gate.sh は mode=live を『VM の command を止めてよい』と読む)。
      // 片方だけ live のときは "partial"。個別の状態は mode_launch / mode_dispatch。
      mode: this.launchLive() && this.dispatchLive() ? "live" : this.launchLive() || this.dispatchLive() ? "partial" : "dry-run",
      mode_launch: this.launchLive() ? "live" : "dry-run",
      mode_dispatch: this.dispatchLive() ? "live" : "dry-run",
      mode_close: this.d.cfg.liveClose ? "live" : "dry-run",
      // 規則 A の候補数 (issue 番号は出さない。記録は counters.wouldClose と log の would-close)。
      auto_close_detected: detectRuleA(this.s).length,
      // 降格 (#2340) の理由。issue 番号だけを含む。降格していなければ null。解除は POST /demote/reset (手動) か、60 分の時限復帰 (auto-stale)。
      demoted_reason: this.meta.demoted?.reason ?? null,
      shadow: this.shadow(),
      // TARGET に数える run の総数 (opencode.yaml の in_progress + queued など。実装・review・fix・oc-pm・watchdog の全て)。active_all と同じ値。
      active_runs: plan.active,
      active_all: plan.active,
      active_impl: plan.active_impl,
      active_other: plan.active_other,
      active_by_event: this.activeRuns().byEvent,
      target: plan.target,
      // 観測から推定した上限を足した目標 (TARGET を超えない)。cap_est は 24 時間以内の推定、無ければ null。
      target_eff: plan.targetEff,
      cap_est: plan.capEst ?? null,
      room: plan.room,
      open_issues: open,
      open_prs: Object.values(this.s.prs).filter((p) => p.state === "open").length,
      phase: plan.phase.review_only ? "review-only" : "launch",
      open_prs_excl_stuck: plan.open_prs_excl_stuck,
      stuck_prs: plan.stuck_prs,
      launch_stop: plan.stop ?? null,
      // IMPORT_REQUIRED=1 のとき、VM の状態を取り込む前は "no-import" (launch しない)。取り込んだ時刻は imported_at (#2343)。
      launch_blocked: plan.blocked ?? null,
      imported_at: this.meta.importedAt ?? null,
      blocked: c("blocked"),
      started: c("started"),
      ready: c("ready"),
      // ready の区分別の件数 (prio:critical / prio:low のラベル。無ければ normal)。合計は ready と一致する。
      ready_by_prio: readyByPrio,
      // 未完了の run を区分別に数えた値 (合計は active_all と一致)。prio:low の上限 (low_cap) は applied (prio:critical が着手済みか launch 可能) のときだけ効く。
      active_by_prio: plan.active_by_prio,
      low_cap: plan.low_cap,
      relaunch: c("relaunch"),
      user: c("user"),
      hold: c("hold"),
      stopped: c("stopped"),
      // 最後の run-outcome が artifact で止まり、新しい素材が無く再投入しないもの (PM の判断待ち)。
      no_pr_needs_pm: rows.stopped.filter(([n]) => (this.s.issues[String(n)]?.labels ?? []).includes("oc:no-pr") && this.s.sig[String(n)]?.outcome?.reason === "artifact").length,
      recent: c("recent"),
      would_launch_now: plan.picks.map((p) => ({ n: p.n, art: p.art, relaunch: p.relaunch })),
      pm_detected: pmDetected,
      stuck: stuckAges.length,
      stuck_age_max_min: stuckAges.length ? Math.max(...stuckAges) : null,
      needs_pm: countLabel(NEEDS_PM_LABEL),
      needs_user: countLabel(NEEDS_USER_LABEL),
      no_pr_by_reason: noPrByReason,
      // 実装 run が PR も出さずに連続して打ち切られ (cancelled / failure / timed_out)、自動の再着手を止めた open issue の件数と番号 (oc-pm の no_pr で PM agent に回す)。
      killed_stopped: this.killedIssues().length,
      killed_issues: this.killedIssues().map(([n]) => n).slice(0, 100),
      refs_only_merge_rate_24h: { merged: mergedDay.length, refs_only: refsOnly, rate: mergedDay.length ? refsOnly / mergedDay.length : null },
      open_issues_delta_24h: base ? open - base.open : null,
      pm_dispatch_1h: this.pmHistory().filter((h) => now - h.at < 3_600_000).length,
      // 直近 1 時間の oc-pm の送信数を kind 別に (合計は pm_dispatch_1h と同じ。refs_orphan の最低配分 (KIND_MIN_PER_HOUR) が効いたかを見る #3704)。
      pm_dispatch_1h_by_kind: this.pmDispatch1hByKind(now),
      // pm_dispatch_1h の内訳 (区分別。合計は pm_dispatch_1h と一致する)。
      pm_dispatch_1h_by_prio: pmByPrio,
      // oc-pm の毎時上限 (PM_LIMITS.hourMax) と、直近 24 時間にその上限で見送った件数 (対象ごと・tick ごとの回数。pmDispatch と haltNotify が数える)。
      pm_dispatch_cap: PM_LIMITS.hourMax,
      // 停止行の直接の再投入 (wake・CI-250) の config と、直近 1 時間の投稿数・dry-run の記録数。除外は needs-user-input・prio:critical・open な子持ち。
      wake: { per_h: this.d.cfg.wakePerH, ref_day_max: this.d.cfg.wakeRefDayMax, live: this.launchLive(), sent_1h: this.wakeHistory(now, "wakeLive").filter((h) => now - h.at < 3_600_000).length, would_1h: this.wakeHistory(now, "wakeWould").filter((h) => now - h.at < 3_600_000).length },
      pm_skipped_hour_24h: this.pmHourSkips(now).reduce((sum, h) => sum + h.n, 0),
      // dry-run で『送るはずだった』oc-pm (直近 24 時間。kind と ref だけ)。LIVE_DISPATCH では空。
      would_dispatch_pm: this.dispatchLive() ? [] : this.pmHistory().map((h) => ({ kind: h.kind, ref: h.ref, at: iso(h.at) })),
      last_full_sync: this.meta.fullSyncAt ? iso(this.meta.fullSyncAt) : null,
      last_reconcile: this.meta.reconcileAt ? iso(this.meta.reconcileAt) : null,
      last_watchdog: this.meta.watchdogAt ? iso(this.meta.watchdogAt) : null,
      last_tick: this.meta.tickAt ? iso(this.meta.tickAt) : null,
      fresh: this.fresh(),
      counters,
      last_webhook_at: this.meta.lastWebhookAt ? iso(this.meta.lastWebhookAt) : null,
      last_dispatch_at: this.meta.lastDispatchAt ? iso(this.meta.lastDispatchAt) : null,
      last_digest_at: this.meta.digestAt ? iso(this.meta.digestAt) : null,
      // 失敗した webhook 配送の回収 (#2339)。件数は counters.redelivered (送った) と counters.wouldRedeliver (LIVE_REDELIVER 未設定で送らなかった)。
      last_redeliver_scan: this.meta.redeliverAt ? iso(this.meta.redeliverAt) : null,
      hook_failed_last_scan: this.meta.redeliverFailed ?? null,
      running,
      // 全 event の queued・pending・waiting の数と、最も古い queued の経過分 (queued が無ければ null)。
      queued: cnt.queued,
      oldest_queued_age_min: cnt.oldestMin,
      // 直近 24 時間の tick ごとの in_progress の最大値 (観測が無ければ null)。
      peak_running: peakRunning(this.obs, now) ?? null,
      // 投稿したが 5 分たっても run が現れなかった issue。自動では再投稿しない (人が見る)。
      launch_unobserved: this.launchUnobserved(),
      // dry-run のために投稿しなかった GitHub への書き込み (/oc 投稿 + repository_dispatch) の累計。
      dry_run_skipped_posts: counters.wouldLaunch + counters.wouldDispatch,
      reconcile_diff: this.meta.reconcileDiff ?? { last: 0, total: 0 },
      // 率制限の判定 (#2345)。alert は 2 回連続で条件を満たしたとき true。rate_limit_30m は直近の評価の窓 (30 分) の件数と割合 (評価が無ければ null)。通知はしない。
      rate_limit_alert: this.meta.rateAlert?.alert === true,
      rate_limit_30m: this.meta.rateAlert
        ? {
            count: this.meta.rateAlert.count,
            total: this.meta.rateAlert.total,
            rate: this.meta.rateAlert.total ? this.meta.rateAlert.count / this.meta.rateAlert.total : null,
            streak: this.meta.rateAlert.streak,
            at: iso(this.meta.rateAlert.at),
          }
        : null,
      rest_remaining: rest?.remaining ?? null,
      rest_used: rest?.used ?? null,
      rest_reset_at: rest?.reset !== undefined ? iso(rest.reset * 1000) : null,
      sync_truncated: Object.entries(this.meta.syncTruncated ?? {}).map(([name, v]) => ({ name, pages: v.pages, at: v.at })),
      last_full_sync_rest_calls: this.meta.fullSyncCalls ?? null,
      last_full_sync_comment_rest_calls: this.meta.fullSyncCommentCalls ?? null,
      comment_window_h: this.d.cfg.commentWindowH,
      comment_max_pages: this.d.cfg.commentMaxPages,
      last_error: lastError,
      log: this.log.slice(-20).map((l) => (l.note === undefined ? l : { ...l, note: this.clean(l.note) })),
      ...extra,
    };
  }
}
