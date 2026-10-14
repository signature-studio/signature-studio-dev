// issue / PR 本文から issue 番号の参照を取る純関数 (親子の判定 #2336 と、規則 A の merged PR の判定に使う)。
// 本文は保存で切る前の全文を渡すこと (webhook.ts の body は 3000 字で切るため、切った後では参照を取りこぼす)。

// 親 issue の宣言: 本文の『親: #N』行。最初の #番号を親とする (classify.ts の親子の判定と同じ語彙)。
export function parentOf(body: string): number | null {
  const m = /^親\s*[:：]\s*(.+)$/m.exec(body);
  if (!m) return null;
  const first = /#(\d+)/.exec(m[1]);
  return first ? Number(first[1]) : null;
}

// Closes / Fixes / Resolves / Refs のキーワードで参照する issue 番号 (重複なし・昇順)。
export function closeRefs(body: string): number[] {
  const re = /\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s*:?\s+#(\d{1,7})\b/gi;
  return uniqSorted([...body.matchAll(re)].map((m) => Number(m[1])));
}

// 本文・題名に現れる #番号 (重複なし・昇順)。キーワードの有無は問わない。件数で切らない (切ると言及を取りこぼし、規則 A が親を閉じる側に外れる)。
export function mentionRefs(text: string): number[] {
  return uniqSorted([...text.matchAll(/#(\d{1,7})\b/g)].map((m) => Number(m[1])));
}

const uniqSorted = (xs: number[]): number[] => [...new Set(xs)].sort((a, b) => a - b);
