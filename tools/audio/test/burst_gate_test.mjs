// AU-38 (#3432): burst_runs > 0 の判定 (harness/burst.mjs) を mock の結果で確かめる (実機・ブラウザ不要)。
// 使い方: node tools/audio/test/burst_gate_test.mjs
import { burstStats, burstGate } from "../harness/burst.mjs";

const check = (ok, msg) => { console.log(`${ok ? "PASS" : "FAIL"} ${msg}`); if (!ok) process.exitCode = 1; };
const hist = (...kv) => { const h = new Array(32).fill(0); for (let i = 0; i < kv.length; i += 2) h[kv[i]] = kv[i + 1]; return h; };
const asio = (stats, extra = {}) => ({ api: "asio", stats, ...extra });

// 正常: burst_hist が取れている
const good = asio({ burst_hist: hist(0, 900, 2, 99) });
check(burstGate(good)[0] === true, "正常な burst_hist (runs>0) は PASS");

// 取得失敗: burst_hist が無い (worklet の ctl ビュー範囲外で読めなかった場合の結果)
check(burstGate(asio({ underruns: 0, silence_frames: 0 }))[0] === false, "burst_hist 無し (取得失敗) は FAIL");

// 取得失敗: burst_hist が全 bin 0 (Atomics.add が飲まれた場合。p99 = 0)
const zero = asio({ burst_hist: new Array(32).fill(0) });
check(burstGate(zero)[0] === false, "burst_hist 全 0 (runs=0・p99=0) は FAIL");
check(burstStats(zero.stats.burst_hist).burst_p99 === 0, "全 0 の p99 は 0 (従来はこれを見ず PASS していた)");

// 他 API・abort・stats 無しは対象外
check(burstGate({ api: "ds", stats: {} })[0] === true, "api=ds は対象外 (PASS)");
check(burstGate({ api: "wasapi", stats: {} })[0] === true, "api=wasapi は対象外 (PASS)");
check(burstGate({ api: "asio", aborted: true })[0] === true, "abort 結果は対象外 (PASS。abort の判定は各 expect)");
check(burstGate({ api: "asio" })[0] === true, "stats 無しは対象外 (PASS)");

// p99 の式は従来どおり (bin 上端)
const p = burstStats(hist(0, 99, 1, 1));
check(p.burst_runs === 100 && p.burst_p99 === 512, `p99 は該当 bin の上端 (runs=${p.burst_runs} p99=${p.burst_p99})`);

process.exit(process.exitCode ?? 0);
