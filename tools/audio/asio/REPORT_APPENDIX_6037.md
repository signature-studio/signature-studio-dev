# tools/audio/asio — AU-50 (#6037) 停止時の時系列計装と停止の主体の切り分け 付録

親: [REPORT.md](REPORT.md) §8 / #3757 / #2777 (#3757 残件)。前提: [REPORT_APPENDIX_4593.md](REPORT_APPENDIX_4593.md) (memset 区間の 127 ms はスレッド未実行時間と読める)。

## 1. 計装 (判定は変えない)

| 場所 | 内容 |
|---|---|
| `tools/audio/src/flasio.c` | producer 周期ごとに `[notify_ms, fill, underruns, wake, cb0, cb1, wr]` を静的配列 (2048 行) に記録。時刻は `fla_now_ms` (epoch ms)。`fla_ctl_t` の外に置き共有 SAB の layout は変えない |
| `public/worklets/fl-audio-worklet.js` | `underrun_trace` に `ms: Date.now()` を追加 (consumer の underrun 時刻) |
| `src/runtime/audio-shim.ts` | `underrunLog` に `ms` を保持 |
| `tools/audio/asio/harness/com_page.mjs` | main thread の heartbeat (5 ms 周期、20 ms 超の間隔を `hb_gaps` へ) と、`tl` / `ul_ms` (underrun 時刻と worklet 直近 64 quantum の `recs`) を結果 JSON へ |

すべて同じ epoch ms の時計 (`performance.timeOrigin + now`。worklet は `Date.now()`)。

## 2. 測定

測定 commit: `6b5ddfd22` (計装を入れた最後の commit)。

- 負荷: `yes > /dev/null` × 4 (PID を控えて終了後に PID 指定で `kill`)。
- 対象: `node tools/audio/asio/harness/run_com.mjs --only com_ramp_b256_d2`。

### 2-1. 計装コード上の負荷下の試行 (作業ツリーの途中版を含む)

| 試行 | 結果 | underrun 時刻の producer 状態 |
|---|---|---|
| r6037_load1 | underruns=1 silence=3712 | fill 0・producer wake 間隔 101.6 ms (worklet `recs` なし) |
| r6037_load2 | underruns=1 silence=2560 | fill 0・producer wake 間隔 91.7 ms (worklet `recs` なし) |
| r6037_L1〜L5 | 0 / 5 | — |
| r6037_load4 | 個別の結果は未記録 (下記 注) | — |
| r6037_L6〜L8 | 0 / 3 | — |
| r6037_L9 | underruns=1 silence=256 (ramp 117,632 mismatch) | fill 0・producer wake 間隔 62.5 ms |

- 試行は `6b5ddfd22` と作業ツリー途中版のどちらで取ったかを区別して記録していない (両方を含む)。HEAD `6b5ddfd22` の 6/6 PASS (§2-2) とは別の試行として扱う。
- 計装途中版 (`recs` が入る前) の試行 (load1・load2) は、worklet の直近 quantum が JSON に入っていない。`recs` が取れたのは L9 だけ。
- load3 は試行後に出力欠落を確認して除外した。分母 12 はこの除外後の数 (load1・load2・load4・L1〜L9)。load4 の個別の結果は記録が無い。underrun 3 回の内訳は load1・load2・L9 として記録されている。

### 2-2. 計装 commit `6b5ddfd22` 上の負荷下 (本 PR の HEAD)

| 試行 | 結果 |
|---|---|
| c6b5_L1〜L6 | 6 / 6 PASS (underruns 0・silence 0・ramp 0 mismatch) |

計装途中版 (§2-1) は負荷下 12 回 (load1・load2・load4・L1〜L9。load3 は試行後に除外) で underrun 3 回。HEAD `6b5ddfd22` は 6 回で 0 回。母数が小さく、HEAD での再現は確認できていない (§4 参照)。

## 3. 停止の時間帯の切り分け (L9 の 1 例)

underrun を基準 (0 ms) とした相対時刻。

| 系 | 観測 |
|---|---|
| worklet (consumer) | 直近 64 quantum のすべてで `rd` が進む。直近 61 ms の quantum 間隔 `dms` は最大 13 ms・合計 60 ms。停止なし |
| producer (flasio thread) | producer 列の `wr` (epoch ms) は underrun +1.4 ms まで書き込み。その後の wake は +8.5 ms・+17.7 ms と間を空けて、最後に +56.5 ms。区間の最大 wake 間隔は 62.5 ms (`cb0`/`cb1` の計算は 0.00〜0.02 ms)。worklet 側の `wr` (rd/wr のサンプル index) は 122880 で止まる (producer 列の値ではない) |
| main thread heartbeat | 下限 20 ms 超の間隔は underrun 後 [+210, +247, +271] ms と [-3232〜-2934] ms のみ。停止の時間帯 [-100, +60] ms に gap は無い |
| 区間内の seg 最大 (run 全体) | memset 2780 µs・out_write 2225 µs・bufferswitch 2375 µs (1 run の最大。区間は計算の仕事量より桁違いに長い) |

読み (n=1: L9 のみ、計装途中版での 1 回。HEAD `6b5ddfd22` の 6/6 PASS とは別の試行): producer の wake 間隔は 62.5 ms。直近 61 ms では worklet に停止は見られない (最大 13 ms)。ただし直近 64 quantum (約 171 ms 分) には worklet の 41 ms の quantum 間隔が 1 つあり、その位置は未確認のため、停止の時間帯との重なりは言えない。したがって停止の主体は未確定。producer が OS に preempt されたのか、`wait32` の返りが遅れたのかは、記録点が wake と書き込み完了の 2 点のみのためこの計装では区別できない。
L9 では producer の wake 間隔 62.5 ms に加えて、-139.9 ms の 41.7 ms gap もあった。consumer の 41 ms と時刻は一致しない。

## 4. 結論と未解決 (#6037 受入)

- **停止の主体**: 未確定。n=1 (計装途中版) では producer の wake 間隔 62.5 ms、直近 61 ms では worklet に停止なし。171 ms 窓の worklet 41 ms 間隔は位置未確定のため、停止の主体は決められない。
- **直接経路**: 特定できなかった。「wasm スレッドの preempt」か「producer が wake 後に実行を得られなかった」かは、今の計装では区別できない (区間内に記録点が無い)。
- **受入 1 (#6037)**: 部分達成。wasm 側 (producer) の時系列と worklet/main の時系列は同じ epoch ms で記録した。JS 側 bufferSwitchTimeInfo の呼出し時刻は未計装 (producer `cb0`/`cb1` で代替)。
- **未解決**:
  - 負荷下の失敗頻度が測定ごとに揺れる (計装途中版で 3/12、HEAD で 0/6)。母数が小さく、HEAD での再現は未確認。
  - JS 側 bufferSwitchTimeInfo の独立した呼出しログは追加していない (上記)。
  - 床の値 (`FLA_F_T_FLOOR`) は変えていない (PM 判断)。
