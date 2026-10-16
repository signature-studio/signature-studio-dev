// Cloudflare の Custom Dashboard 用の観測ログ (CI-229)。tick の 1 回ごとに 1 行の `{"m":"metrics",...}` を出す。
// 値は /status と同じ集計 (status()) から取る。数値・真偽・列挙・ISO 時刻だけを入れ、自由文は入れない。
export const METRICS_KEYS = [
  "m", "ts", "fresh", "mode", "phase", "demoted", "rate_guard", "stop", "blocked",
  "active", "active_impl", "active_other", "active_critical", "active_normal", "active_low",
  "target", "target_eff", "cap_est", "room",
  "ready", "ready_critical", "ready_normal", "ready_low",
  "would_launch_now", "holds", "runs_running", "runs_queued", "peak_running",
  "launched", "dispatched", "pm_dispatched", "closed", "rest_remaining",
] as const;

export function metricsRow(s: Record<string, any>, ts: string, demoted: boolean, rateGuard: boolean): Record<string, unknown> {
  const c = s.counters ?? {};
  const act = s.active_by_prio ?? {};
  const rdy = s.ready_by_prio ?? {};
  return {
    m: "metrics",
    ts,
    fresh: s.fresh === true,
    mode: s.mode,
    phase: s.phase,
    demoted,
    rate_guard: rateGuard,
    stop: s.launch_stop ?? null,
    blocked: s.launch_blocked ?? null,
    active: s.active_all,
    active_impl: s.active_impl,
    active_other: s.active_other,
    active_critical: act.critical ?? 0,
    active_normal: act.normal ?? 0,
    active_low: act.low ?? 0,
    target: s.target,
    target_eff: s.target_eff,
    cap_est: s.cap_est ?? null,
    room: s.room,
    ready: s.ready,
    ready_critical: rdy.critical ?? 0,
    ready_normal: rdy.normal ?? 0,
    ready_low: rdy.low ?? 0,
    would_launch_now: (s.would_launch_now ?? []).length,
    holds: (s.launch_holds ?? []).length,
    runs_running: s.running?.in_progress ?? 0,
    runs_queued: s.queued ?? 0,
    peak_running: s.peak_running ?? null,
    launched: c.launched ?? 0,
    dispatched: c.dispatched ?? 0,
    pm_dispatched: c.pmDispatched ?? 0,
    closed: c.closed ?? 0,
    rest_remaining: s.rest_remaining ?? null,
  };
}

// 必須キーのうち行に無いものを返す (空なら揃っている)。
export function missingMetricsKeys(row: Record<string, unknown>): string[] {
  return METRICS_KEYS.filter((k) => !(k in row));
}

// Workers Analytics Engine (AE) へ書く 1 データポイントの写像 (CI-230)。AE の上限は indexes 1 / blobs 20 / doubles 20。
// 順序は README の『Analytics Engine』表と一致させる (test/metrics.test.ts が順序を固定する)。
export const AE_INDEXES = ["pm"] as const;
export const AE_BLOBS = ["mode", "phase"] as const;
export const AE_DOUBLES = [
  "active", "active_impl", "active_other", "active_critical", "active_normal", "active_low",
  "target", "target_eff", "room", "ready", "would_launch_now", "holds", "runs_running", "runs_queued",
] as const;

export interface AeDataPoint {
  indexes: string[];
  blobs: string[];
  doubles: number[];
}

export interface AeSink {
  writeDataPoint(p: AeDataPoint): void;
}

// 行を AE の 1 データポイントにする。null や欠けた数値は 0 (AE は数値のみ受けるため)。
export function aePoint(row: Record<string, unknown>): AeDataPoint {
  return {
    indexes: [...AE_INDEXES],
    blobs: AE_BLOBS.map((k) => String(row[k] ?? "")),
    doubles: AE_DOUBLES.map((k) => {
      const v = row[k];
      return typeof v === "number" && Number.isFinite(v) ? v : 0;
    }),
  };
}
