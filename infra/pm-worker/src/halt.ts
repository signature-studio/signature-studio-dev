// launch を止めている条件の判定と、止まっている区間の記録 (#2795)。純関数 (時刻・保管先は呼び出し側が渡す)。
// 止まっている区間の起点 (since) は DO の meta に保存する。条件が 0 になったら消し、次の区間の起点に使い回さない。

// 『止まったまま』とみなす時間。15 分以上止まり、かつ着手待ち (ready) と空き枠 (room) があれば /status.launch_halted_overdue。
export const HALT_OVERDUE_MS = 15 * 60_000;
// 30 分止まったら PM agent へ 1 回だけ知らせる (同じ停止区間では繰り返さない)。
export const HALT_NOTIFY_MS = 30 * 60_000;

export interface HaltInput {
  // VM の状態を取り込む前 (IMPORT_REQUIRED=1 のときだけ起きる)。plan.blocked = no-import。
  noImport: boolean;
  // plan.stop。stuck-ceiling (oc:stuck の PR が多すぎる) か rate-guard (REST 残量が少ない)。
  stop?: string;
  // Review-Only (open PR が多すぎる)。意図した停止だが、新規の着手は空になる。
  reviewOnly: boolean;
  // 同期が古い・一覧を打ち切った。launch は書かない (launch() の fresh の分岐)。
  stale: boolean;
}

// 止めている条件。先頭が /status.launch_halted.reason。止めていなければ空。
export function haltReasons(x: HaltInput): string[] {
  const out: string[] = [];
  if (x.noImport) out.push("no-import");
  if (x.stop) out.push(x.stop);
  if (x.reviewOnly) out.push("review-only");
  if (x.stale) out.push("stale");
  return out;
}

export interface Halt {
  since: string;
  reasons: string[];
  // PM agent への通知を送った (試行した) 時刻。同じ停止区間では 1 回だけ。
  notifiedAt?: string;
}

// 停止の区間を次の tick の状態に進める。止まり続けているときは since と notifiedAt を残し、理由だけ更新する。
export function nextHalt(prev: Halt | undefined, reasons: string[], now: string): Halt | undefined {
  if (reasons.length === 0) return undefined;
  if (!prev) return { since: now, reasons };
  return { ...prev, reasons };
}

export function haltOverdue(since: string | undefined, now: number, ready: number, room: number): boolean {
  if (!since) return false;
  return now - Date.parse(since) >= HALT_OVERDUE_MS && ready > 0 && room > 0;
}

export function haltNotifyDue(halt: Halt | undefined, now: number): boolean {
  return !!halt && !halt.notifiedAt && now - Date.parse(halt.since) >= HALT_NOTIFY_MS;
}
