import manualDepsJson from "../../../tools/pm/manual_deps.json" with { type: "json" };
import { DEFAULT_BATCH } from "./launch.ts";
import { DEFAULT_MARK_LOGIN, DEFAULT_REVIEWER_LOGIN } from "./webhook.ts";

// 既定の TARGET は 58: 同時に走らせる opencode.yaml の run の総数 (実装・review・fix・oc-pm・watchdog の全て。active.ts) の上限。
// GitHub の同時実行の上限 (60) から 2 を残す (oc-pm・watchdog と、投稿直後でまだ run が現れていない分の余裕)。
// 実際の目標は、観測から推定した上限を足した target_eff (saturation.ts。TARGET を超えない)。
export const DEFAULT_TARGET_WORKER = 58;
export const DEFAULT_QUEUE_MARGIN = 10;
export const DEFAULT_TARGET_MIN = 30;
export const DEFAULT_REPO = "signature-studio/signature-studio-dev";

export const MIN_COMMENT_WINDOW_H = 24;
export const DEFAULT_COMMENT_WINDOW_H = 24;
export const DEFAULT_COMMENT_MAX_PAGES = 80;
// oc:no-pr の再着手の間隔 (時間)。最後の報告・/oc の投稿からこの時間が過ぎるまで再着手しない。wrangler.toml の NO_PR_COOLDOWN_H と揃える (test/active.test.ts が両方を見る)。
export const DEFAULT_NO_PR_COOLDOWN_H = 6;
// prio:low の issue の未完了の run の上限 (LOW_CAP)。wrangler.toml の LOW_CAP と揃える (test/active.test.ts が両方を見る)。
export const DEFAULT_LOW_CAP = 10;

export interface Env {
  PM: { idFromName(n: string): unknown; get(id: unknown): { fetch(r: Request): Promise<Response> } };
  // Worker の secret binding (32 バイトの base64url)。App の private key / webhook secret の暗号化鍵。DO の外にだけある。
  STORE_KEY: string;
  REPO?: string;
  ORG?: string;
  TARGET?: string;
  // 同時実行の上限 (推定) に足す余裕 (既定 10) と、target_eff の下限 (既定 30)。TARGET は上限のまま。
  QUEUE_MARGIN?: string;
  TARGET_MIN?: string;
  BATCH?: string;
  // "1" のときだけ GitHub へ書き込む。それ以外 (未設定を含む) は dry-run。
  // LIVE は launch (/oc コメント) と dispatch (repository_dispatch) の両方を一度に切り替える従来のスイッチ。
  // LIVE_LAUNCH / LIVE_DISPATCH は個別のスイッチで、設定されていれば LIVE より優先する (設定値が "1" 以外なら dry-run)。
  LIVE?: string;
  LIVE_LAUNCH?: string;
  LIVE_DISPATCH?: string;
  // 規則 A の自動 close (autoclose.ts) を実行するか。"1" のときだけ。LIVE には従わない (close は副作用が大きいので個別に明示する)。
  LIVE_CLOSE?: string;
  // "1" のときだけ、失敗した webhook 配送を GitHub に再配送する (POST /app/hook/deliveries/{id}/attempts)。LIVE には従わない (単独のスイッチ・#2339)。
  LIVE_REDELIVER?: string;
  // 実装 App (bot) のログイン。bot_last (最後の報告) の判定に使う。
  BOT_LOGIN?: string;
  // 停止印 (oc-fix-limit) の作者。型 Bot でこの login の投稿だけを停止として信じる (既定 github-actions[bot]。#2639)。
  MARK_LOGIN?: string;
  // PM の人間アカウント (PAT)。PM App の bot ログインは slug から自動で加える。
  PM_LOGINS?: string;
  WATCHDOG_INTERVAL_S?: string;
  RECONCILE_INTERVAL_S?: string;
  NO_PR_COOLDOWN_H?: string;
  // prio:low の未完了の run の上限 (既定 10。空・非数・負は既定に戻す)。prio:critical が着手済みか launch 可能な間だけ効く (launch.ts の LowCap)。
  LOW_CAP?: string;
  // 全体同期でコメントを読む窓 (時間。24 未満は 24 に切り上げる) と、コメント一覧のページ上限 (1 ページ 100 件)。
  COMMENT_WINDOW_H?: string;
  COMMENT_MAX_PAGES?: string;
  // oc:stuck の open PR がこれを超えたら launch を止める (既定 40)。
  STUCK_HIGH?: string;
  // reviewer App の bot ログイン。review の verdict とマーカー付きコメントの信頼に使う。
  REVIEWER_LOGIN?: string;
  // "1" のときだけ、VM の状態 (launched・relaunch・phase・pm_art) を取り込むまで launch しない (#2343)。既定は取り込みを求めない (#2795)。
  // wrangler.toml の [vars] には置かない (本番で既定のまま止まる事故の再発防止)。
  IMPORT_REQUIRED?: string;
  // デプロイした commit hash (`wrangler deploy --var BUILD_COMMIT:<hash>`)。wrangler.toml の [vars] には置かない (渡さなければ未設定)。/status の build に出す。
  BUILD_COMMIT?: string;
}

export interface Config {
  repo: string;
  org: string;
  target: number;
  queueMargin: number;
  targetMin: number;
  batch: number;
  // launch の /oc コメント投稿を実行するか。
  liveLaunch: boolean;
  // repository_dispatch (oc-watchdog と oc-pm) の送信を実行するか。
  liveDispatch: boolean;
  // 規則 A の自動 close を実行するか (LIVE_CLOSE="1" のときだけ。既定は記録のみ)。
  liveClose: boolean;
  // 失敗した webhook 配送の再配送を実行するか (既定 false: 一覧を読んで送るはずだった件数だけ記録する)。
  liveRedeliver: boolean;
  botLogin: string;
  pmLogins: string[];
  watchdogIntervalS: number;
  reconcileIntervalS: number;
  noPrCooldownH: number;
  lowCap: number;
  commentWindowH: number;
  commentMaxPages: number;
  stuckHigh: number;
  reviewerLogin: string;
  markLogin: string;
  // VM の状態を取り込むまで launch しない (#2343)。IMPORT_REQUIRED=1 のときだけ true (#2795 で既定を false に反転)。
  importRequired: boolean;
  // oc-pm の対象にしてよい bot の起票者。人は author_association (OWNER / MEMBER / COLLABORATOR) で絞る。
  pmTargetBots: string[];
  // デプロイした commit hash。未設定・hash の形でない値は null (自由文を /status に出さない)。
  build: string | null;
  manualDeps: Record<string, number[]>;
}

const num = (v: string | undefined, d: number): number => {
  const n = Number(v);
  return v !== undefined && v !== "" && Number.isFinite(n) && n >= 0 ? n : d;
};

const buildCommit = (v: string | undefined): string | null => (v !== undefined && /^[0-9a-f]{7,40}$/.test(v) ? v : null);

// 個別のスイッチが設定されていればそれに従い ("1" だけが live)、未設定のときだけ LIVE に従う。
const liveFlag = (own: string | undefined, legacy: string | undefined): boolean => (own !== undefined ? own === "1" : legacy === "1");

export function loadConfig(env: Partial<Env>, manualDeps: Record<string, number[]> = manualDepsJson as Record<string, number[]>): Config {
  const repo = env.REPO ?? DEFAULT_REPO;
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error("bad REPO");
  return {
    repo,
    org: env.ORG ?? repo.split("/")[0],
    target: num(env.TARGET, DEFAULT_TARGET_WORKER),
    queueMargin: num(env.QUEUE_MARGIN, DEFAULT_QUEUE_MARGIN),
    targetMin: num(env.TARGET_MIN, DEFAULT_TARGET_MIN),
    batch: num(env.BATCH, DEFAULT_BATCH),
    liveLaunch: liveFlag(env.LIVE_LAUNCH, env.LIVE),
    liveDispatch: liveFlag(env.LIVE_DISPATCH, env.LIVE),
    liveClose: env.LIVE_CLOSE === "1",
    liveRedeliver: env.LIVE_REDELIVER === "1",
    botLogin: env.BOT_LOGIN ?? "opencode-for-signature-studio[bot]",
    pmLogins: (env.PM_LOGINS ?? "pycabbage").split(",").map((s) => s.trim()).filter(Boolean),
    watchdogIntervalS: num(env.WATCHDOG_INTERVAL_S, 300),
    reconcileIntervalS: num(env.RECONCILE_INTERVAL_S, 300),
    noPrCooldownH: num(env.NO_PR_COOLDOWN_H, DEFAULT_NO_PR_COOLDOWN_H),
    lowCap: Math.floor(num(env.LOW_CAP?.trim(), DEFAULT_LOW_CAP)),
    // classify が見る bot の報告は 24 時間以内。窓がそれより短いと、取りこぼした報告で誤って着手する。
    commentWindowH: Math.max(MIN_COMMENT_WINDOW_H, num(env.COMMENT_WINDOW_H, DEFAULT_COMMENT_WINDOW_H)),
    commentMaxPages: Math.max(1, Math.floor(num(env.COMMENT_MAX_PAGES, DEFAULT_COMMENT_MAX_PAGES))),
    stuckHigh: num(env.STUCK_HIGH, 40),
    reviewerLogin: env.REVIEWER_LOGIN ?? DEFAULT_REVIEWER_LOGIN,
    markLogin: env.MARK_LOGIN ?? DEFAULT_MARK_LOGIN,
    importRequired: env.IMPORT_REQUIRED === "1",
    pmTargetBots: ["opencode-for-signature-studio[bot]", "oc-reviewer-for-signature-studio[bot]"],
    build: buildCommit(env.BUILD_COMMIT),
    manualDeps,
  };
}
