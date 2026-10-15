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

// PR 本文の Refs と子 issue の親の読み取り (oc-pm の refs_orphan 用)。純関数。本文の自由文は残さず、番号だけを返す。
// Refs のみの判定は pr-lint.sh と同じ語 (Refs #N)。閉じキーワード (Closes / Fixes / Resolves の系) が 1 つでもあれば Refs のみではない。
// 閉じキーワードは `Closes #N`・`Closes:#N`・`Closes owner/repo#N` のいずれも数える。Refs は `Refs #N`・`Refs:#N` を数え、`Refs owner/repo#N` と 8 桁の番号は数えない。
const CLOSE_RE = /(?:^|[^A-Za-z])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*(?:[\w.-]+\/[\w.-]+)?#\d/i;
const REFS_RE = /(?:^|[^A-Za-z])Refs\s*:?\s*#(\d{1,7})(?!\d)/gi;
// 親の読み方は src/classify.ts と tools/pm/launch_issues.py に揃える: 最初の『親:』行の最初の #N だけ。
const PARENT_LINE_RE = /^親\s*[:：]\s*(.+)$/m;
const ISSUE_NO_RE = /#(\d{1,7})(?!\d)/;

// 閉じキーワードの無い本文に書かれた Refs #N の番号 (昇順・重複なし)。閉じキーワードがあれば空。
// Refs のみの判定 (指標 refs_only_merge_rate_24h・refs_orphan) はこの関数だけを使う。
export function refsOnlyNumbers(body: string): number[] {
  if (CLOSE_RE.test(body)) return [];
  const out = new Set<number>();
  for (const m of body.matchAll(REFS_RE)) out.add(Number(m[1]));
  return [...out].sort((a, b) => a - b);
}

// 本文の最初の『親:』行の最初の issue 番号 (親。最大 1 件)。
export function parentNumbers(body: string): number[] {
  const line = PARENT_LINE_RE.exec(body);
  const m = line ? ISSUE_NO_RE.exec(line[1]) : null;
  return m ? [Number(m[1])] : [];
}
