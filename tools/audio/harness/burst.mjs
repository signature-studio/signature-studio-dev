// AU-30 (#3151) / AU-38 (#3432): worklet の burst_hist (512 f 刻み・32 bin, 末尾 bin は以上) から p99 を出し、取得失敗を判定に掛ける。
// run.mjs の判定ループと test/burst_gate_test.mjs が同じ関数を使う。
// p99 は該当 bin の上端 (p99 ≤ この値)。
export const burstStats = (h) => {
  const n = h.reduce((a, b) => a + b, 0), need = Math.ceil(0.99 * n);
  let c = 0;
  for (let k = 0; k < h.length && n; k++) { c += h[k]; if (c >= need) return { burst_runs: n, burst_p99: (k + 1) * 512 }; }
  return { burst_runs: n, burst_p99: 0 };
};

// ASIO 結果 (api=asio) は burst_hist が取れていること (burst_runs > 0) を PASS の条件にする。
// 取得失敗 (hist 無し・全 bin 0) は p99 = 0 のまま判定を通過するため、ここで FAIL にする。他 API の結果は対象外。
export const burstGate = (r) => {
  if (r?.api !== "asio" || r.aborted || !r.stats) return [true, ""];
  const runs = Array.isArray(r.stats.burst_hist) ? burstStats(r.stats.burst_hist).burst_runs : 0;
  return [runs > 0, `burst_runs=${runs}(want >0)`];
};
