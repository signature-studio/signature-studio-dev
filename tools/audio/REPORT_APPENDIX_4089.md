# AU-15 (#4089) 付録: underrun 時刻と write 区間の突き合わせ

測定 commit: `45a37a83c` (fix(audio): producer pw_trace を epoch 軸へ)。`bash tools/audio/integration/e2e.sh` を foreground で実行 (`TMPDIR=$RUNNER_TEMP`)。

- 時間軸 (基準の選び方): **epoch µs 下 32bit に統一する**。worklet は underrun の最初の 1 回を `(Date.now()*1000)|0` で `capture hdr[7]` へ記録。producer の `pw_trace` (tw/td) は、修正前は `emscripten_get_now()` (pthread Worker 内の `performance.now()`・文脈相対) で、worklet の epoch 軸と ~1.7e12 ms ずれていた。修正後は `fla_now_ms()` (= `performance.timeOrigin + performance.now()`、epoch ms、`tools/audio/src/flaudio.c`) を使い、worklet と同じ epoch 軸に揃えた。Worker の `timeOrigin` は page と ~52 ms ずれるが、`timeOrigin+now` の epoch 値は文脈間で ~0.4 ms 以内に揃う (`tools/startup/pump/REPORT.md` §clock_skew)。精度は worklet 側の ms (±1000 µs)。
- 軸検査 (e2e `axis-epoch`・毎 run): producer の最終 write 完了 `done_us` と page の `(Date.now()*1000)|0` の差 (age) が 0 以上 1 s 未満であること。修正前は約 1.7e12 ms の差で必ず FAIL する。
- 判定行: `uo_overlap` (重なり有無)・`uo_gap_us` (0 で区間内、>0 で区間後、<0 で区間前)・`uo_w`・`uo_wake_us`・`uo_done_us`。`underrun=0` の run は `uo_overlap=none`。
- 合成検証: `node tools/audio/integration/uo_negctl.mjs` で `matchUnderrunWrite` を抜き出して実行。正例 3・負例 3・u32 折り返し 2・空 1 の計 9 件 **ALL PASS**。
- 実 e2e (測定 commit `45a37a83c`): 10 run 全 exit 0・15/15 PASS (12〜13 s)。axis-epoch は 20/20 PASS (age 約 14〜26 ms)。
- 実 underrun の判定値: 1 run (run 1 = 初回計測・dev) で underrun 1 件が発生。判定 `uo_overlap=false uo_gap_us=-26075 uo_w=56832 uo_wake_us=1832341555 uo_done_us=1832341570`。underrun は producer の write 区間より 26 ms 前に起きた (producer が 65 ms 止まった後の write で、underrun が先行するのは整合する)。この run の dev:tone/dev:underruns は underrun により FAIL (既知の断続。#863)。
- 10 run の方は underrun 0 件のため `uo_overlap=none`。判定値の再現率は低い (約 1 % 未満)。
