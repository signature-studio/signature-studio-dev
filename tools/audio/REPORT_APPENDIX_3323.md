# REPORT_APPENDIX_3323 — Firefox の burst p99 (AU-37 #3323)

> **正本**: `tools/audio/REPORT_AU2_CI.md` §13。本書はその測定全文。

## A. 変更

- `harness/au2.mjs`: 結果 JSON の `stats.burst_hist` (window.__done が返す fla_test の値) から `burst_p99`・`burst_runs` を求め、`results[]` に `burst_p99`・`burst_runs` を追加。`harness/run.mjs` の `burstStats` と同じ式 (512 f 刻み・p99 は該当 bin の上端)。PASS 判定は変えていない。
- `au2_firefox_summary.mjs`: 表に「burst p99 (f, bin 上端)」列を追加。
- 測定 commit: `db0a788fe` (`feat(audio): AU-2 Firefox の burst p99 を burst_hist から出す (#3323)`)。`git diff db0a788fe HEAD -- tools/audio` の出力は空 (測定後に変更なし)。

## B. 測定 (HEAD `db0a788fe`・n=3)

- 環境: ubuntu runner・Firefox 157.0 (headless)・PulseAudio 16.1 (apt 導入)・既定 sink = `ci_null`・emsdk 6.0.12 (上流。素材 `toolchain-emsdk` は未使用)。
- 再現: `EMSDK_ENV=<emsdk_env.sh> bash tools/audio/build.sh` → `AU2_OUT=tools/audio/results/au37_p99 bash tools/audio/au2_firefox_matrix.sh 3` → `node tools/audio/au2_firefox_summary.mjs tools/audio/results/au37_p99`。
- wall: rep 1 = 41.3 s・rep 2 = 40.6 s・rep 3 = 40.6 s。load avg は各 rep の開始時 0.32 / 0.56 / 0.81 (1 分値)。

| シナリオ | n | PASS | underruns | burst (f) | burst p99 (f) | T (f) | clock (Hz) | sink 接続 |
|---|---|---|---|---|---|---|---|---|
| asio_sine_b256_d2 (48k) | 3 | 3/3 | 0 | 1024 | 1536 | 1536 | 47998–48016 | 3/3 |
| asio_sine_b256_96k (96k) | 3 | 3/3 | 0 | 1920 | 2048 | 2816 | 95992–96004 | 3/3 |
| asio_sine_b512_96k (96k, B=512) | 3 | 3/3 | 0 | 1920 | 2048 | 3072 | 96009–96028 | 3/3 |

- rep 別の burst_runs (n) は 528〜533 (48k)・531〜533 (96k)。probe の `worklet.wait` は既存 §9-2 と同じ結果 (timed-out・20 ms)。
- 注: `burst_hist` の末尾 bin は ≥15872 f を含むため、p99 がそこに入ると 16384 と出る (`REPORT_APPENDIX_3151.md` §12 と同じ制約)。今回の値は末尾に入っていない。

## C. 既存 PASS 判定

- 判定 (underrun 0・silence 0・sine maxErr 1.49e-8・zeroRuns 0・ctx.sampleRate 一致・worklet エラー 0・既定 sink 接続) は変更前と同じ。9/9 PASS。
