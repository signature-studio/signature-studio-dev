// GitHub REST の rate limit。応答ヘッダ (x-ratelimit-*) が正で、`gh api rate_limit` の本文は食い違うことがある。
// ヘッダの無い応答・数値でない値では何も更新しない (Number(null) / Number("") の 0 を『残量 0』と誤読しない)。

// remaining がこれ未満の間は launch を止める (理由 rate-guard)。reconcile の読み取りは続ける。
export const REST_REMAINING_MIN = 1500;
export const RATE_GUARD = "rate-guard";

export interface RateInfo {
  remaining?: number;
  used?: number;
  // 窓が戻る時刻 (epoch 秒)
  reset?: number;
}

const DIGITS = /^\d{1,12}$/;

function num(h: Headers, name: string): number | undefined {
  const v = h.get(name);
  return v !== null && DIGITS.test(v.trim()) ? Number(v.trim()) : undefined;
}

// 有効なヘッダが 1 つも無ければ null。有るものだけを返す。
export function parseRateHeaders(h: Headers): RateInfo | null {
  const r: RateInfo = {};
  const remaining = num(h, "x-ratelimit-remaining");
  const used = num(h, "x-ratelimit-used");
  const reset = num(h, "x-ratelimit-reset");
  if (remaining !== undefined) r.remaining = remaining;
  if (used !== undefined) r.used = used;
  if (reset !== undefined) r.reset = reset;
  return Object.keys(r).length ? r : null;
}

// 未観測 (undefined) は止めない。1,499 で止め、1,500 で継続する。
export function restGuardOn(remaining: number | undefined | null): boolean {
  return typeof remaining === "number" && remaining < REST_REMAINING_MIN;
}
