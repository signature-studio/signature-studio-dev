# AU-30 (#3151) P2 burst p99 の測定 (付録)

親: `REPORT_AU2_CI.md` §11。250 行上限のため分割移動 (内容は削除していない)。

## 11. P2 の p99 (AU-30 #3151)

- **測定 commit**: `e403fd7a` (コードを変えた最後の commit。worklet・ctl・ハーネス・集計)。`git diff --stat e403fd7a HEAD -- tools/audio/src tools/audio/test tools/audio/harness tools/audio/build.sh tools/audio/au2_summary.mjs public/worklets src/runtime` の出力は測定 commit 時点で 0 行。ただし main 取り込み後の HEAD では 0 行ではない: `d55d2c45` 時点で 5 files・70 insertions(+)・7 deletions(-) (main 側の AU-29・AU-32 の変更)、現 HEAD `8310689a` 時点で 9 files・229 insertions(+)・11 deletions(-)。`e403fd7a` の値は現 HEAD の値ではない。全行列の再測定は §11-3、部分の再測定は §11-2。
- **方式**: worklet は連続 `process()` の run (Date.now 差 ≤1 ms) が終わるたびに `burst_hist[floor(len/512)]` (ctl @384、`FLA_CTL_SIZE` 384→512) を +1 する。末尾 bin は ≥15872 f。`run.mjs` は p99 を該当 bin の上端で出す (512 f 刻み。真の p99 はこの値以下) → 結果 JSON の `stats.burst_p99`・`stats.burst_runs`。run には待機中の 128 f 単独 run も入る (fake 48k の bin 0 は 1499 run 中 364。発生源は未切り分け)。
- **再現**: `bash tools/audio/build.sh` → `AU2_OUT=tools/audio/results/au30_p99 bash tools/audio/au2_matrix.sh 3` → `node tools/audio/au2_summary.mjs tools/audio/results/au30_p99`。環境: ubuntu runner (4 vCPU), google-chrome 154.0.8037.97, PulseAudio 16.1 (apt 導入)。生結果: `results/au30_p99/`。

### 11-1 行列 (n=3, 測定 commit `e403fd7a`)

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

### 11-2 main 取り込み後の HEAD の再測定 (測定 commit `d55d2c45`)

- **理由**: `e403fd7a` の後に main が測定対象コードを変えた (AU-29 の clock_jump 診断 `ct`・`pn`・`cb`、AU-32 の集計の出力名対応、新規テスト `worklet_jump_check.mjs`)。WORKFLOW §6 により、差分のあるコードを現 HEAD で再測定した。
- **差分 (測定 commit → HEAD)**: `git diff --stat e403fd7a HEAD -- tools/audio/src tools/audio/test tools/audio/harness tools/audio/build.sh tools/audio/au2_summary.mjs public/worklets src/runtime` の出力:

```
 public/worklets/fl-audio-worklet.js     |  3 +-
 src/runtime/audio-shim.ts               |  7 ++--
 tools/audio/au2_summary.mjs             |  6 ++--
 tools/audio/harness/run.mjs             |  2 +-
 tools/audio/test/worklet_jump_check.mjs | 59 +++++++++++++++++++++++++++++++++
 5 files changed, 70 insertions(+), 7 deletions(-)
```

- **環境**: ubuntu runner (4 vCPU)・google-chrome 154.0.8037.97・emsdk 6.0.12 (上流 `emscripten-core/emsdk` から導入。素材 `toolchain-emsdk` は本 run の素材に無かった)・PulseAudio 16.1 (apt。`pulseaudio -D` 後に `module-null-sink sink_name=ci_null` を既定 sink)。
- **build**: `EMSDK_ENV=<emsdk>/emsdk_env.sh bash tools/audio/build.sh` → `[audio] build OK` (HEAD `d55d2c45`)。
- **実行**: `node tools/audio/harness/run.mjs --only asio_sine_b256_d2,asio_sine_b256_96k` を PulseAudio 無し (1 rep) と null-sink (1 rep) で実行。null-sink の 48k は `--only asio_sine_b256_d2` で 2 rep 追加 (計 3 rep)。`results.json` は run ごとに退避し、コミットしていない。

| 条件 | シナリオ | n | PASS | underrun | burst max (f) | burst p99 (f, bin 上端) | 実 T (f) | sine maxErr |
|---|---|---|---|---|---|---|---|---|
| PulseAudio 無し (Chrome 既定出力) | asio_sine_b256_d2 (48k) | 1 | 1/1 | 0 | 512 | 1024 | 1024 | 1.49e-8 |
| PulseAudio 無し | asio_sine_b256_96k | 1 | 1/1 | 0 | 1024 | 1536 | 2816 | 1.49e-8 |
| null-sink (`ci_null`) | asio_sine_b256_d2 (48k) | 3 | 3/3 | 0 | 1152 (3 rep とも) | 1536 | 1792 | 1.49e-8 |
| null-sink | asio_sine_b256_96k | 1 | 1/1 | 0 | 4480 | 3584 | 5888 | 1.49e-8 |

- **wall と load**: 2 シナリオの run の wall は 89.2 s (PulseAudio 無し, load 0.41→0.20)・80.8 s (null-sink r1, load 0.31→0.10)。
- **結論**: null 48k は 3/3 PASS (underrun 0・silence 0)。受入 3 の null 48k 条件は現 HEAD で満たす。null 96k は n=1 の PASS で p99 は §11-1 と同値の 3584。burst 最大値は rep ごとに揺れる (§11-1 の 3456 に対し今回 4480)。PulseAudio 無しの 48k は 1/1 PASS で、§11-1 の fake 48k rep 1 の FAIL (underrun 1) は今回再現していない。1 rep のため原因の切り分けは未実施 (#187)。
- **未実施**: 行列の全行は §11-3 (測定 commit `8310689a`) で測り直した。この節 §11-2 は部分の再測定で、行列の n=3 の値は §11-3 を正とする。
- **最終 HEAD での確認**: main の 2 回目の取り込み (`origin/main` `7c85004e`) で `run.mjs` が変わった (`--browser` の分岐・Linux の `pactl get-default-sink` の読取り・JSON の `browser`・`default_output`)。Chrome の経路は同一 (`withBrowser = withChrome`)。`git diff --stat d55d2c45 4ca74476 -- tools/audio/src tools/audio/test tools/audio/harness tools/audio/build.sh tools/audio/au2_summary.mjs public/worklets src/runtime` = 5 files・159 insertions(+)・4 deletions(-) (Safari 用ファイルの追加と `run.mjs`)。同 HEAD で null-sink の `--only asio_sine_b256_d2,asio_sine_b256_96k` を再実行: **2/2 PASS** (48k: underrun 0・burst 1152・p99 1536・T 1792 / 96k: underrun 0・burst 4480・p99 3584・T 5888・sine maxErr 1.49e-8・`default_output` = `ci_null`)。
- **Safari の mock テスト**: `SAFARIDRIVER=tools/audio/test/safaridriver_mock.mjs node tools/audio/test/safari_mock_test.mjs` → rc 0 (PASS 全行)。

### 11-3 全行列の再測定 (測定 commit `8310689a`・受入 2 の全行)

- **理由**: round 3 の review (blocking 1)。測定 commit から現 HEAD までの測定対象コードの差分が残り、行列の 6 行が 1 つの測定 commit で測られていなかったため、行列を測り直した。
- **測定 commit**: `8310689a` (測定対象コードを最後に変えた commit は `4ca74476` 以前。`git diff 4ca74476 8310689a -- <範囲>` の出力は 0 行)。**`git diff 8310689a HEAD -- tools/audio/src tools/audio/test tools/audio/harness tools/audio/build.sh tools/audio/au2_summary.mjs public/worklets src/runtime` の出力は 0 行** (測定後の commit は docs のみ)。
- **環境**: ubuntu runner (4 vCPU)・google-chrome 154.0.8037.97 (headless)・PulseAudio 16.1 (apt 導入。fake は `pulseaudio -k` で停止、null は `module-null-sink sink_name=ci_null` を既定 sink)・emsdk 6.0.12 (上流 `emscripten-core/emsdk`。素材 `toolchain-emsdk` は本 run の素材に無し)。
- **build**: `EMSDK_ENV=/home/runner/work/_temp/emsdk/emsdk_env.sh bash tools/audio/build.sh` → `[audio] build OK`。
- **実行**: `AU2_OUT=tools/audio/results/au30_p99_r2 bash tools/audio/au2_matrix.sh 3` (exit 0・wall 00:09:58 → 00:20:38 = 10 分 40 秒)。生結果は `results/au30_p99_r2/` (各 run の `host` に load 値)。集計: `node tools/audio/au2_summary.mjs tools/audio/results/au30_p99_r2`。
- **load avg (1 分値)**: 行列の開始 (fake_r1) 0.61 → 終了 (`nc_soak15_negctl`) 0.06。
- **結果** (`au2_summary.mjs` の出力):

| 条件 | sr | シナリオ | n | PASS | underrun (合計) | burst max (f) | burst p99 (f, bin 上端) | 実 T (f) | T_req (f) | T≥T_req | baseLatency (ms) | outputLatency (ms) | clock (Hz, 平均) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Chrome fake シンク | 48000 | asio_sine_b256_d2 | 3 | 2/3 | 1 | 512 | 1024 | 1024〜1536 | 1024 | OK | 10.0 | 30.0 | 48000.0 |
| Chrome fake シンク | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 1024 | 1536 | 2816 | 1536 | OK | 10.0 | 30.0 | 96000.2 |
| Chrome fake シンク | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 1024 | 1536 | 3072 | 2048 | OK | 10.0 | 30.0 | 96000.3 |
| Chrome PulseAudio null-sink | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 1152 | 1536 | 1792 | 1792 | OK | 11.6 | 31.0〜36.0 | 48019.7 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 3456〜5632 | 3584 | 4608〜7424 | 7424 | OK | 11.6 | 72.0〜84.0 | 96006.2 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 4480 | 3584 | 6144 | 6144 | OK | 11.6 | 68.0〜69.0 | 95983.0 |

- **PASS**: null-sink は 3 条件 × 3 rep = 9/9 PASS (underrun 0・silence 0・sine maxErr 1.49e-8)。受入 3 の null 48k は 3/3。
- **FAIL 1 件 (未解決・#187)**: fake_r1 の `asio_sine_b256_d2` で underrun 1・silence 640・sine maxErr 5.88e-1。§11-1 (`e403fd7a`) の fake_r1 も同条件で underrun 1・silence 128・maxErr 6.85e-1 だった。rep 1 にだけ出ており、rep 2・3 は PASS。原因は未切り分け (#187)。
- **p99 (bin 上端)**: fake 48k 1024・fake 96k 1536・null 48k 1536・null 96k 3584。各条件の 3 rep で同値。
- **fake の `default_output`**: `pactl` 接続失敗 (PulseAudio を止めた条件の意図どおり)。null の run は `ci_null`。
- **NC**: `nc_soak15_negctl` は FAIL (exit 1・underrun 7・silence 3712・ramp mismatch 669952/720896)。期待どおり。
- **未実施**: Firefox の p99 (子 [AU-37] #3323)・30 分ソークの p99 (#187)。
