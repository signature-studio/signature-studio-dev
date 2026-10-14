# AU-30 (#3151) P2 burst p99 の測定 (付録)

親: `REPORT_AU2_CI.md` §10。250 行上限のため分割移動 (内容は削除していない)。

## 10. P2 の p99 (AU-30 #3151)

- **測定 commit**: `e403fd7a` (コードを変えた最後の commit。worklet・ctl・ハーネス・集計)。`git diff --stat e403fd7a HEAD -- tools/audio/src tools/audio/test tools/audio/harness tools/audio/build.sh tools/audio/au2_summary.mjs public/worklets src/runtime` の出力は 0 行 (測定後に増えたのはこの REPORT と結果 JSON だけ)。
- **方式**: worklet は連続 `process()` の run (Date.now 差 ≤1 ms) が終わるたびに `burst_hist[floor(len/512)]` (ctl @384、`FLA_CTL_SIZE` 384→512) を +1 する。末尾 bin は ≥15872 f。`run.mjs` は p99 を該当 bin の上端で出す (512 f 刻み。真の p99 はこの値以下) → 結果 JSON の `stats.burst_p99`・`stats.burst_runs`。run には待機中の 128 f 単独 run も入る (fake 48k の bin 0 は 1499 run 中 364。発生源は未切り分け)。
- **再現**: `bash tools/audio/build.sh` → `AU2_OUT=tools/audio/results/au30_p99 bash tools/audio/au2_matrix.sh 3` → `node tools/audio/au2_summary.mjs tools/audio/results/au30_p99`。環境: ubuntu runner (4 vCPU), google-chrome 154.0.8037.97, PulseAudio 16.1 (apt 導入)。生結果: `results/au30_p99/`。

### 10-1 行列 (n=3, 測定 commit `e403fd7a`)

| 条件 | sr | シナリオ | n | PASS | underrun (合計) | burst max (f) | burst p99 (f, bin 上端) | 実 T (f) | T_req (f) | T≥T_req | baseLatency (ms) | outputLatency (ms) | clock (Hz, 平均) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Chrome fake シンク | 48000 | asio_sine_b256_d2 | 3 | 2/3 | 1 | 512 | 1024 | 1024〜1536 | 1024 | OK | 10.0 | 30.0 | 48000.0 |
| Chrome fake シンク | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 1024 | 1536 | 2816 | 1536 | OK | 10.0 | 30.0 | 95999.7 |
| Chrome fake シンク | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 1024 | 1536 | 3072 | 2048 | OK | 10.0 | 30.0 | 96000.0 |
| Chrome PulseAudio null-sink | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 1152 | 1536 | 1792 | 1792 | OK | 11.6 | 31.0〜36.0 | 48017.9 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 3456 | 3584 | 4608 | 4608 | OK | 11.6 | 81.0〜83.0 | 96008.8 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 4480〜5504 | 3584 | 6144〜7680 | 7680 | OK | 11.6 | 68.0〜71.0 | 95989.8 |

- **受入 3 (null 48k の PASS 判定)**: `asio_sine_b256_d2` の null-sink は 3/3 PASS (underrun 0・silence 0・sine maxErr 1.49e-8)。
- **p99 と最大値**: 最大値は 1 run の外れ値になりうる。例: null 96k・B=512 は 393〜394 run。最大 5504 f は r1・r2 で各 1 run、4480 f は r3 で 1 run。p99 はいずれも 3584 (bin 3072〜3584)。
- **FAIL 1 件 (未解決)**: fake_r1 の `asio_sine_b256_d2` で underrun 1・silence 128・sine maxErr 6.85e-1 (fake 48k は 2/3 PASS)。症状は §5-4 の fake_r1 (underrun 1) と同じ。今回は 1 回のみで、原因は未切り分け (#187)。null 48k では出ていない。
- **NC**: `nc_soak15_negctl` は FAIL (exit 1・underrun 7・silence 3712・ramp mismatch 669952/720896)。§5-4 の NC と同値で、期待どおり。
- **未実施**: Firefox の p99 (`harness/au2.mjs` は `burst_obs` のみ)・30 分ソークの p99 (#187)。
