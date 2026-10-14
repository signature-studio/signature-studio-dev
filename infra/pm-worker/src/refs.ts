// issue / PR 本文から issue 番号の参照を取る純関数 (親子の判定 #2336 と、規則 A の merged PR の判定に使う)。
// 本文は保存で切る前の全文を渡すこと (webhook.ts の body は 3000 字で切るため、切った後では参照を取りこぼす)。

const MENTION_CAP = 200;

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

// 本文・題名に現れる #番号 (先頭から MENTION_CAP 件まで・重複なし・昇順)。キーワードの有無は問わない。
export function mentionRefs(text: string): number[] {
  const seen: number[] = [];
  for (const m of text.matchAll(/#(\d{1,7})\b/g)) {
    const n = Number(m[1]);
    if (!seen.includes(n)) seen.push(n);
    if (seen.length >= MENTION_CAP) break;
  }
  return seen.sort((a, b) => a - b);
}

const uniqSorted = (xs: number[]): number[] => [...new Set(xs)].sort((a, b) => a - b);
