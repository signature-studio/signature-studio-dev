import manualDepsJson from "../../../tools/pm/manual_deps.json" with { type: "json" };
import { DEFAULT_BATCH } from "./launch.ts";
import { DEFAULT_REVIEWER_LOGIN } from "./webhook.ts";

// 既定の TARGET は 80。GitHub の同時 job 上限 (60) を超えた分は queued になり、常時 60 に張り付くための余裕。
export const DEFAULT_TARGET_WORKER = 80;

export const MIN_COMMENT_WINDOW_H = 24;
export const DEFAULT_COMMENT_WINDOW_H = 24;
export const DEFAULT_COMMENT_MAX_PAGES = 80;

export interface Env {
  PM: { idFromName(n: string): unknown; get(id: unknown): { fetch(r: Request): Promise<Response> } };
  // Worker の secret binding (32 バイトの base64url)。App の private key / webhook secret の暗号化鍵。DO の外にだけある。
  STORE_KEY: string;
  REPO?: string;
  ORG?: string;
  TARGET?: string;
  BATCH?: string;
  // "1" のときだけ GitHub へ書き込む。それ以外 (未設定を含む) は dry-run。
  // LIVE は launch (/oc コメント) と dispatch (repository_dispatch) の両方を一度に切り替える従来のスイッチ。
  // LIVE_LAUNCH / LIVE_DISPATCH は個別のスイッチで、設定されていれば LIVE より優先する (設定値が "1" 以外なら dry-run)。
  LIVE?: string;
  LIVE_LAUNCH?: string;
  LIVE_DISPATCH?: string;
  // 実装 App (bot) のログイン。bot_last (最後の報告) の判定に使う。
  BOT_LOGIN?: string;
  // PM の人間アカウント (PAT)。PM App の bot ログインは slug から自動で加える。
  PM_LOGINS?: string;
  WATCHDOG_INTERVAL_S?: string;
  RECONCILE_INTERVAL_S?: string;
  NO_PR_COOLDOWN_H?: string;
  // 全体同期でコメントを読む窓 (時間。24 未満は 24 に切り上げる) と、コメント一覧のページ上限 (1 ページ 100 件)。
  COMMENT_WINDOW_H?: string;
  COMMENT_MAX_PAGES?: string;
  // oc:stuck の open PR がこれを超えたら launch を止める (既定 40)。
  STUCK_HIGH?: string;
  // reviewer App の bot ログイン。review の verdict とマーカー付きコメントの信頼に使う。
  REVIEWER_LOGIN?: string;
  // デプロイした commit hash (`wrangler deploy --var BUILD_COMMIT:<hash>`)。wrangler.toml の [vars] には置かない (渡さなければ未設定)。/status の build に出す。
  BUILD_COMMIT?: string;
}

export interface Config {
  repo: string;
  org: string;
  target: number;
  batch: number;
  // launch の /oc コメント投稿を実行するか。
  liveLaunch: boolean;
  // repository_dispatch (oc-watchdog と oc-pm) の送信を実行するか。
  liveDispatch: boolean;
  botLogin: string;
  pmLogins: string[];
  watchdogIntervalS: number;
  reconcileIntervalS: number;
  noPrCooldownH: number;
  commentWindowH: number;
  commentMaxPages: number;
  stuckHigh: number;
  reviewerLogin: string;
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
  const repo = env.REPO ?? "signature-studio/signature-studio-dev";
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error("bad REPO");
  return {
    repo,
    org: env.ORG ?? repo.split("/")[0],
    target: num(env.TARGET, DEFAULT_TARGET_WORKER),
    batch: num(env.BATCH, DEFAULT_BATCH),
    liveLaunch: liveFlag(env.LIVE_LAUNCH, env.LIVE),
    liveDispatch: liveFlag(env.LIVE_DISPATCH, env.LIVE),
    botLogin: env.BOT_LOGIN ?? "opencode-for-signature-studio[bot]",
    pmLogins: (env.PM_LOGINS ?? "pycabbage").split(",").map((s) => s.trim()).filter(Boolean),
    watchdogIntervalS: num(env.WATCHDOG_INTERVAL_S, 300),
    reconcileIntervalS: num(env.RECONCILE_INTERVAL_S, 300),
    noPrCooldownH: num(env.NO_PR_COOLDOWN_H, 3),
    // classify が見る bot の報告は 24 時間以内。窓がそれより短いと、取りこぼした報告で誤って着手する。
    commentWindowH: Math.max(MIN_COMMENT_WINDOW_H, num(env.COMMENT_WINDOW_H, DEFAULT_COMMENT_WINDOW_H)),
    commentMaxPages: Math.max(1, Math.floor(num(env.COMMENT_MAX_PAGES, DEFAULT_COMMENT_MAX_PAGES))),
    stuckHigh: num(env.STUCK_HIGH, 40),
    reviewerLogin: env.REVIEWER_LOGIN ?? DEFAULT_REVIEWER_LOGIN,
    pmTargetBots: ["opencode-for-signature-studio[bot]", "oc-reviewer-for-signature-studio[bot]"],
    build: buildCommit(env.BUILD_COMMIT),
    manualDeps,
  };
}
