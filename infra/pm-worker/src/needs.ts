// reviewer の差し戻しが PM の判断・起票を求めているかの語彙。tools/pm/pm_needs.py の KEY と同じ正規表現・同じ行分割。
// 突き合わせ: test/needs_crosscheck.py + test/fixtures/needs.input.json (Python 版の KEY を直接読む)。
export const NEEDS_KEY = /PM 判断|PM に求める|PM が決め|PM の決定|起票依頼|PM 起票|PM 採番|PM 承認|PM が .*(起票|判断)/;

// Python の str.splitlines() と同じ区切り (\n \r \r\n \v \f \x1c \x1d \x1e \x85 \u2028 \u2029)。
const PY_LINE_BREAK = /\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/;

export function splitLines(s: string): string[] {
  const parts = s.split(PY_LINE_BREAK);
  if (parts.length > 0 && parts[parts.length - 1] === "") parts.pop();
  return parts;
}

// KEY に一致した行の数。0 なら PM 判断を求めていない。
export function needsHits(body: string): number {
  let n = 0;
  for (const line of splitLines(body)) if (NEEDS_KEY.test(line)) n++;
  return n;
}

export const needsPmDecision = (body: string | null | undefined): boolean => needsHits(body ?? "") > 0;
