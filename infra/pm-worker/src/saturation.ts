// GitHub の同時実行の上限を観測から推定し、launch の目標 (target_eff) を決める (純関数のみ。時刻は引数で渡す)。
// 上限は Team の契約で変わる (60 → 20 など) ので、固定の TARGET だけでは queued が際限なく積まれる。

export const SAT_WINDOW_MS = 24 * 3_600_000;
// queued > 0 のまま running が同じ値で続いた時間。これ以上続いたときだけ飽和とみなす。
export const SAT_FLAT_MS = 30 * 60_000;

// t: 観測時刻 (epoch ms)。r: in_progress の数。q: queued・pending・waiting の数。1 分ごとに 1 件 (同じ分は後の値で置き換える)。
export interface Sample {
  t: number;
  r: number;
  q: number;
}

// value: 推定の上限 (run 数)。at: 最後に更新した時刻 (飽和を観測した時、または上限を引き上げた時)。
export interface Cap {
  value: number;
  at: number;
}

// 直近の飽和を判定する。queued > 0 のまま running が最新と同じ値で SAT_FLAT_MS 以上続いていれば、その running を返す。
export function saturatedRunning(obs: Sample[]): number | undefined {
  const last = obs[obs.length - 1];
  if (!last || last.q <= 0) return undefined;
  let first = last;
  for (let i = obs.length - 2; i >= 0; i--) {
    const x = obs[i];
    if (x.q <= 0 || x.r !== last.r) break;
    first = x;
  }
  return last.t - first.t >= SAT_FLAT_MS ? last.r : undefined;
}

// 上限の推定。飽和していれば今の running で更新する。飽和していなくても、上限を記録したあとの peak が上限を超えたら引き上げる。
// 上限の記録から 24 時間たって更新が無ければ推定は消える (古い peak で上限を押し上げ続けない)。
export function nextCap(cap: Cap | undefined, obs: Sample[], now: number): Cap | undefined {
  const cur = capValue(cap, now) === undefined ? undefined : cap;
  const sat = saturatedRunning(obs);
  if (sat !== undefined) return { value: sat, at: now };
  if (!cur) return undefined;
  let peak = 0;
  for (const x of obs) if (x.t >= cur.at && x.r > peak) peak = x.r;
  return peak > cur.value ? { value: peak, at: now } : cur;
}

// 有効な推定の上限 (記録から 24 時間以内のものだけ)。無ければ undefined。
export function capValue(cap: Cap | undefined, now: number): number | undefined {
  return cap && now - cap.at < SAT_WINDOW_MS ? cap.value : undefined;
}

// target_eff = clamp(cap_est + margin, min, target)。推定が無ければ target のまま。下限より上限 (target) を優先する。
export function targetEff(cap: number | undefined, target: number, margin: number, min: number): number {
  return cap === undefined ? target : Math.min(target, Math.max(min, cap + margin));
}

// 24 時間以内の観測の peak。観測が無ければ undefined。
export function peakRunning(obs: Sample[], now: number): number | undefined {
  let peak: number | undefined;
  for (const x of obs) if (now - x.t < SAT_WINDOW_MS && (peak === undefined || x.r > peak)) peak = x.r;
  return peak;
}

// 1 件追加する。同じ分の観測は置き換え、24 時間より古いものは捨てる。
export function appendSample(obs: Sample[], s: Sample, now: number): Sample[] {
  const kept = obs.filter((x) => now - x.t < SAT_WINDOW_MS);
  const last = kept[kept.length - 1];
  if (last && Math.floor(last.t / 60_000) === Math.floor(s.t / 60_000)) return [...kept.slice(0, -1), s];
  return [...kept, s];
}
