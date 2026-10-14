import manualDepsJson from "../../../tools/pm/manual_deps.json" with { type: "json" };
import { DEFAULT_BATCH } from "./launch.ts";
import { DEFAULT_REVIEWER_LOGIN } from "./webhook.ts";

// 既定の TARGET は 58: 同時に走らせる opencode.yaml の run の総数 (実装・review・fix・oc-pm・watchdog の全て。active.ts) の目標。
// GitHub の同時実行の上限 (60) から 2 を残す (oc-pm・watchdog と、投稿直後でまだ run が現れていない分の余裕)。
export const DEFAULT_TARGET_WORKER = 58;
export const DEFAULT_REPO = "signature-studio/signature-studio-dev";

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
  // "1" のときだけ、失敗した webhook 配送を GitHub に再配送する (POST /app/hook/deliveries/{id}/attempts)。LIVE には従わない (単独のスイッチ・#2339)。
  LIVE_REDELIVER?: string;
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
  // 失敗した webhook 配送の再配送を実行するか (既定 false: 一覧を読んで送るはずだった件数だけ記録する)。
  liveRedeliver: boolean;
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
  manualDeps: Record<string, number[]>;
}

const num = (v: string | undefined, d: number): number => {
  const n = Number(v);
  return v !== undefined && v !== "" && Number.isFinite(n) && n >= 0 ? n : d;
};

// 個別のスイッチが設定されていればそれに従い ("1" だけが live)、未設定のときだけ LIVE に従う。
const liveFlag = (own: string | undefined, legacy: string | undefined): boolean => (own !== undefined ? own === "1" : legacy === "1");

export function loadConfig(env: Partial<Env>, manualDeps: Record<string, number[]> = manualDepsJson as Record<string, number[]>): Config {
  const repo = env.REPO ?? DEFAULT_REPO;
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error("bad REPO");
  return {
    repo,
    org: env.ORG ?? repo.split("/")[0],
    target: num(env.TARGET, DEFAULT_TARGET_WORKER),
    batch: num(env.BATCH, DEFAULT_BATCH),
    liveLaunch: liveFlag(env.LIVE_LAUNCH, env.LIVE),
    liveDispatch: liveFlag(env.LIVE_DISPATCH, env.LIVE),
    liveRedeliver: env.LIVE_REDELIVER === "1",
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
    manualDeps,
  };
}
