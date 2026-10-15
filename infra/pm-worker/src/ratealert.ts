// 率制限の判定 (#2345・CI-66) の定数と、マーカーの読み取り。REST は呼ばない (マーカーは webhook と同期で保存済み)。
// マーカーは record-run-outcome.sh (implement) と detect-rate-limit.sh (review / fix) が出す `cause=rate_limit run=<run id>` (CI-65 #2344)。

// 直近この時間に完了した opencode.yaml の run を窓にする。
export const RATE_WINDOW_MS = 30 * 60_000;
// 件数が RATE_MIN_COUNT 以上、かつ窓の全 run に占める割合が RATE_MIN_PERCENT (%) 以上で『条件を満たす』。
export const RATE_MIN_COUNT = 5;
export const RATE_MIN_PERCENT = 30;
// 条件を満たす評価が RATE_STREAK 回連続したら alert。
export const RATE_STREAK = 2;
// 評価の間隔。alarm と cron の 2 つの tick が 1 分に重なっても 1 回と数える。
export const RATE_EVAL_GAP_MS = 50_000;
// これより間が空いた評価は連続とみなさない (Worker が止まっていた間の評価を続けて数えない)。
export const RATE_EVAL_MAX_GAP_MS = 150_000;

const RATE_MARK_RE = /<!-- oc-run-outcome:([^>]*)-->/g;
const CAUSE_RE = /(?:^|\s)cause=rate_limit(?=\s|$)/;
const RUN_RE = /(?:^|\s)run=(\d{1,15})(?=\s|$)/;

// コメント本文の oc-run-outcome マーカーに cause=rate_limit と run=<id> があれば、その run id を返す。
export function rateMarkRun(body: string): number | undefined {
  for (const m of body.matchAll(RATE_MARK_RE)) {
    if (!CAUSE_RE.test(m[1])) continue;
    const r = RUN_RE.exec(m[1]);
    if (r) return Number(r[1]);
  }
  return undefined;
}

export function rateHit(count: number, total: number): boolean {
  return count >= RATE_MIN_COUNT && count * 100 >= total * RATE_MIN_PERCENT;
}
