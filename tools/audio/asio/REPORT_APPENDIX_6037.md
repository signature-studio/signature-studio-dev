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
| r6037_load1 | underruns=1 silence=3712 | fill 0・producer wake 間隔 101.6 ms |
| r6037_load2 | underruns=1 silence=2560 | fill 0・producer wake 間隔 91.7 ms (+4 ms) |
| r6037_L1〜L5 | 0 / 5 | — |
| r6037_L6〜L8 | 0 / 3 | — |
| r6037_L9 | underruns=1 silence=256 (ramp 117,632 mismatch) | fill 0・producer wake 間隔 62.5 ms (+1.4 ms) |

計装コードの途中版 (`recs` が入る前) の試行 (load1・load2) は、worklet の直近 quantum が JSON に入っていない。`recs` が取れたのは L9 だけ。

### 2-2. 計装 commit `6b5ddfd22` 上の負荷下 (本 PR の HEAD)

| 試行 | 結果 |
|---|---|
| c6b5_L1〜L6 | 6 / 6 PASS (underruns 0・silence 0・ramp 0 mismatch) |

計装途中版 (§2-1) は負荷下 12 回 (load1・load2・load4・L1〜L9。load3 は出力欠落のため除外) で underrun 3 回。HEAD `6b5ddfd22` は 6 回で 0 回。母数が小さく、HEAD での再現は確認できていない (§4 参照)。

## 3. 停止の時間帯の切り分け (L9 の 1 例)

underrun を基準 (0 ms) とした相対時刻。

| 系 | 観測 |
|---|---|
| worklet (consumer) | 直近 64 quantum のすべてで `rd` が進む。直近 61 ms の quantum 間隔 `dms` は最大 13 ms・合計 60 ms。停止なし |
| producer (flasio thread) | +1.4 ms まで書き込み。その後 `wr` が 122880 で止まり、次の wake は +8.5 ms・+17.7 ms と間を空けて、最後に +56.5 ms。区間の最大 gap は 62.5 ms (`cb` の計算は 0.00〜0.02 ms) |
| main thread heartbeat | 下限 20 ms 超の間隔は underrun 後 [+210, +247, +271] ms と [-3232〜-2934] ms のみ。停止の時間帯 [-100, +60] ms に gap は無い |
| 区間内の seg 最大 (run 全体) | memset 2780 µs・out_write 2225 µs・bufferswitch 2375 µs (1 run の最大。区間は計算の仕事量より桁違いに長い) |

読み: underrun の直前 61 ms については、**worklet も main thread も止まっていない**。producer は書き込みの間隔が伸び、wait を抜けてから次の書き込みまでの区間が 60 ms を超えた。ただしこの計装では、producer が OS に preempt されたのか、`wait32` の返りが遅れたのかは分けられない (記録点が wake と書き込み完了の 2 点のみ)。なお worklet の直近 64 quantum (約 171 ms 分) には 41 ms の quantum 間隔が 1 つあった。直近 61 ms の最大は 13 ms で、41 ms はそれより前に起きている (正確な位置は未確認)。
L9 では producer の +1.4 ms の 62.5 ms gap に加えて、-139.9 ms の 41.7 ms gap もあった。consumer の 41 ms と時刻は一致しない。

## 4. 結論と未解決 (#6037 受入)

- **停止の主体**: 観測された範囲では producer thread 側。worklet (consumer) と main thread は停止の時間帯に動いていた。
- **直接経路**: 「wasm スレッドの preempt」か「producer が wake 後に実行を得られなかった」かは、今の計装では区別できない (区間内に記録点が無い)。特定できなかった範囲は、producer が `wait32` を抜けた後の OS スケジューリング。
- **未解決**:
  - 負荷下の失敗頻度が測定ごとに揺れる (計装途中版で 3/15、HEAD で 0/6)。母数が小さく、HEAD での再現は未確認。
  - JS 側 bufferSwitchTimeInfo の呼出し時刻は、producer の `cb0`/`cb1` で代替 (同じ epoch ms)。JS 側の独立した呼出しログは追加していない。
  - 床の値 (`FLA_F_T_FLOOR`) は変えていない (PM 判断)。
