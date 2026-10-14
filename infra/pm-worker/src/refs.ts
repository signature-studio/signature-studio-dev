// PR 本文の Refs と子 issue の親の読み取り (oc-pm の refs_orphan 用)。純関数。本文の自由文は残さず、番号だけを返す。
// Refs のみの判定は pr-lint.sh と同じ語 (Refs #N)。閉じキーワード (Closes / Fixes / Resolves の系) が 1 つでもあれば Refs のみではない。
const CLOSE_RE = /(?:^|[^A-Za-z])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*#\d/i;
const REFS_RE = /(?:^|[^A-Za-z])Refs\s*:?\s*#(\d{1,7})(?!\d)/gi;
const PARENT_LINE_RE = /^親[:：](.*)$/gm;
const ISSUE_NO_RE = /#(\d{1,7})(?!\d)/g;

// 閉じキーワードの無い本文に書かれた Refs #N の番号 (昇順・重複なし)。閉じキーワードがあれば空。
export function refsOnlyNumbers(body: string): number[] {
  if (CLOSE_RE.test(body)) return [];
  const out = new Set<number>();
  for (const m of body.matchAll(REFS_RE)) out.add(Number(m[1]));
  return [...out].sort((a, b) => a - b);
}

// 本文の `親: #N` の行に出る issue 番号 (親の候補。昇順・重複なし)。
export function parentNumbers(body: string): number[] {
  const out = new Set<number>();
  for (const line of body.matchAll(PARENT_LINE_RE)) for (const m of line[1].matchAll(ISSUE_NO_RE)) out.add(Number(m[1]));
  return [...out].sort((a, b) => a - b);
}
