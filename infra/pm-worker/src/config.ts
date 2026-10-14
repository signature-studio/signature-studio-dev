import manualDepsJson from "../../../tools/pm/manual_deps.json" with { type: "json" };
import { DEFAULT_BATCH } from "./launch.ts";

// 既定の TARGET は 80。GitHub の同時 job 上限 (60) を超えた分は queued になり、常時 60 に張り付くための余裕。
export const DEFAULT_TARGET_WORKER = 80;

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
  // oc:stuck の open PR がこれを超えたら launch を止める (既定 40)。
  STUCK_HIGH?: string;
}

export interface Config {
  repo: string;
  org: string;
  target: number;
  batch: number;
  // launch の /oc コメント投稿を実行するか。
  liveLaunch: boolean;
  // repository_dispatch (oc-watchdog) の送信を実行するか。
  liveDispatch: boolean;
  botLogin: string;
  pmLogins: string[];
  watchdogIntervalS: number;
  reconcileIntervalS: number;
  noPrCooldownH: number;
  stuckHigh: number;
  manualDeps: Record<string, number[]>;
}

const num = (v: string | undefined, d: number): number => {
  const n = Number(v);
  return v !== undefined && v !== "" && Number.isFinite(n) && n >= 0 ? n : d;
};

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
    stuckHigh: num(env.STUCK_HIGH, 40),
    manualDeps,
  };
}
