// 規則 A: merged PR を持つ親 issue の自動 close (#2336)。判定は保存状態だけで行う (REST は呼ばない)。書き込みは engine.ts の autoClose が行う。
// 規則 (全てを満たす open issue N を閉じる):
//   1. N を Closes / Refs / Fixes で参照する merged PR がある
//   2. N を親 (『親: #N』) とする open の子 issue が 1 つ以上ある (残りの作業は子が追跡している)
//   3. N に needs-user-input が付いていない
//   4. N を参照する open PR がない (題名・本文の #N の言及で判定)
//   5. N を blocker にしている open issue が、N の子以外にない
// 保存状態の抜けは『閉じない』に倒す: open PR に mentions が無い (移行前の保存値)、blocked_by の一覧が件数に足りない open issue があるときは閉じない。
import { parentOf } from "./refs.ts";
import { NEEDS_USER_LABEL, type PmState } from "./webhook.ts";

export const AUTO_CLOSE_RULE = "A";
// 1 tick に閉じる上限。
export const AUTO_CLOSE_MAX = 5;
// 同じ issue を試す間隔 (閉じ損ねても、この間は再試行しない。コメントの二重投稿を防ぐ)。
export const AUTO_CLOSE_RETRY_MS = 24 * 3_600_000;
// dry-run の記録の重複排除 (同じ候補を毎分ログに残さない)。
export const AUTO_CLOSE_WOULD_MS = 3 * 3_600_000;

export interface CloseTarget {
  // 閉じる親 issue
  n: number;
  // 参照している merged PR (最小の番号)
  mergedPr: number;
  // open な子 (最小の番号)
  child: number;
}

export function closeComment(t: CloseTarget): string {
  return `[auto-close] 規則 ${AUTO_CLOSE_RULE}: merged PR #${t.mergedPr}、残りは #${t.child} が追跡 <!-- oc-auto-close: rule=${AUTO_CLOSE_RULE} -->`;
}

const asc = (a: number, b: number): number => a - b;

export function detectRuleA(s: PmState): CloseTarget[] {
  const openPrs = Object.values(s.prs).filter((p) => p.state === "open");
  // mentions の無い open PR (保存形式の移行前) が残る間は判定しない。参照中の親を閉じないため。
  if (openPrs.some((p) => p.mentions === undefined)) return [];
  const openIssues = Object.values(s.issues)
    .filter((i) => i.state === "open")
    .sort((a, b) => asc(a.number, b.number));
  const open = new Set(openIssues.map((i) => i.number));

  const kids = new Map<number, number[]>();
  for (const i of openIssues) {
    const p = parentOf(i.body);
    if (p === null || p === i.number || !open.has(p)) continue;
    kids.set(p, [...(kids.get(p) ?? []), i.number]);
  }

  // blocker -> それを待つ open issue (blocked 側が open のものだけ)。
  const waiting = new Map<number, number[]>();
  for (const [k, list] of Object.entries(s.blockedBy)) {
    const blocked = Number(k);
    if (!open.has(blocked)) continue;
    for (const b of list) waiting.set(b, [...(waiting.get(b) ?? []), blocked]);
  }
  // blocked_by の一覧が不明な open issue (件数 total_blocked_by が一覧の件数より多い。件数だけ更新されて blocked_by_added の配送が欠けた形)。どの親を待たせているか分からないので、子でない限り全体で閉じない。
  const unknown = openIssues.filter((i) => i.blockedByCount > (s.blockedBy[String(i.number)]?.length ?? 0)).map((i) => i.number);

  const mergedBy = new Map<number, number[]>();
  for (const p of Object.values(s.prs)) {
    if (p.state !== "closed" || !p.merged) continue;
    for (const n of p.closes ?? []) mergedBy.set(n, [...(mergedBy.get(n) ?? []), p.number]);
  }

  const out: CloseTarget[] = [];
  for (const i of openIssues) {
    const n = i.number;
    if (i.labels.includes(NEEDS_USER_LABEL)) continue;
    const children = (kids.get(n) ?? []).sort(asc);
    if (children.length === 0) continue;
    const prs = (mergedBy.get(n) ?? []).sort(asc);
    if (prs.length === 0) continue;
    if (openPrs.some((p) => (p.mentions ?? []).includes(n))) continue;
    const isChild = new Set(children);
    if ((waiting.get(n) ?? []).some((k) => !isChild.has(k))) continue;
    if (unknown.some((k) => k !== n && !isChild.has(k))) continue;
    out.push({ n, mergedPr: prs[0], child: children[0] });
  }
  return out;
}
