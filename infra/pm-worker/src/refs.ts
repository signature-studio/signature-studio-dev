// PR 本文の Refs と子 issue の親の読み取り (oc-pm の refs_orphan 用)。純関数。本文の自由文は残さず、番号だけを返す。
// Refs のみの判定は pr-lint.sh と同じ語 (Refs #N)。閉じキーワード (Closes / Fixes / Resolves の系) が 1 つでもあれば Refs のみではない。
// 閉じキーワードは `Closes #N`・`Closes:#N`・`Closes owner/repo#N` のいずれも数える。
const CLOSE_RE = /(?:^|[^A-Za-z])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*(?:[\w.-]+\/[\w.-]+)?#\d/i;
const REFS_RE = /(?:^|[^A-Za-z])Refs\s*:?\s*#(\d{1,7})(?!\d)/gi;
// 親の読み方は src/classify.ts と tools/pm/launch_issues.py に揃える: 最初の『親:』行の最初の #N だけ。
const PARENT_LINE_RE = /^親\s*[:：]\s*(.+)$/m;
const ISSUE_NO_RE = /#(\d{1,7})(?!\d)/;

// 閉じキーワードの無い本文に書かれた Refs #N の番号 (昇順・重複なし)。閉じキーワードがあれば空。
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
