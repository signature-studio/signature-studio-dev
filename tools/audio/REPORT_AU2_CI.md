# AU-2 (#187) CI 代理指標の測定 (ubuntu runner)

親: `REPORT.md` §8。実機でしか測れない項目は [AU-22] (#2366) に分離済み。

## 1. 代理経路の検証 (PulseAudio null-sink) — 未検証 (fake と同一の値に留まった, n=1)

| 項目 | 値 |
|---|---|
| 環境 | ubuntu runner (4 vCPU, 15 GiB), `google-chrome 155.0.8059.39` (REPORT の 154 とは版が違う), PulseAudio 16.1 (apt 導入) |
| PulseAudio | `module-null-sink sink_name=ci_null` を起動 (`pactl info` の Default Sink = `ci_null`) |
| 比較 | `asio_sine_b256_d2` を同一ハーネス・同一 HEAD (`1ddc8512`) で 2 回 (fake シンク / PulseAudio 起動中) |

| 条件 | sampleRate | baseLatency | outputLatency | clock (Hz) | burst | T | 判定 |
|---|---|---|---|---|---|---|---|
| fake シンク (既定) | 48000 | 0.011625 s | 0.036 s | 47969.0 | 1152 | 1792 | PASS |
| PulseAudio null-sink 起動中 | 48000 | 0.011625 s | 0.036 s | 47971.0 | 1152 | 1792 | PASS |

**結論**: Chrome の `baseLatency` / `outputLatency` / `burst` / `T` は PulseAudio 起動の有無で変わらず、`clock` も 2 Hz の差に留まった (各条件 n=1)。ただし Chrome の sink-input が `ci_null` に接続したかは **未確認** (`pactl list sink-inputs` は未取得)。そのため「null-sink は代理にならない」とは結論できず、「fake と同一の値に留まった。接続先は未検証」とだけ書く。よって P1〜P4 を null-sink の代理として扱う前提は未検証のままである。Firefox は当時 `tools/audio/harness` が Chrome CDP 専用で測れなかったが、§5 の BiDi 経路で測定済み (#2540)。

## 2. ベースライン `e2e.sh --quick` (main `1ddc8512`, 測定 commit = `1ddc8512`)

- 実行: `bash tools/audio/e2e.sh --quick`, `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh`, `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`
- 結果: **43/44 PASS**, wall 266.9 s, load avg 開始 2.25 → 終了 0.42 (nproc 4)
- FAIL: `asio_ramp_b128_d2` — `underruns=1 silence=2688; ramp mismatches=162944/192384`。B=128 の ramp は本 run で再現。原因は未切り分け (負荷起因の疑い、未確認)。追跡先: #187 (§4)
- burst 分布 (quick, 48k): 512f 大半。96k は 1024f (`asio_sine_b256_96k`, `asio_sine_b512_96k`)。96k/B=256 の `burst_floor=4096` ネガコントロールは PASS (T=5376)

## 3. 未実施 (この run の時間内に収まらないため)

- フル `e2e.sh` (約 9 分 + ASIO COM 経路 約 3 分) と 30 分ソーク: 行列にすると 1 run の 58 分上限を超えるため未実施
- Firefox 行列: §5 で測定済み (#2540・n=3)
- Windows / macOS runner の仮想オーディオ workflow: 未着手 (権限・検証手段の確認が先)

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Chrome が null-sink に接続したか未確認。報告値は fake と同一 (§1) | CI で OS 経路を測る代理指標の成否が未確定 | #187 (AU-2) 内で sink-input の確認と n≥3 の再測定を検討 |
| Chrome の 96k 行が未測定 (Firefox 行は §5 で解決) | 行列 {Chrome, Firefox} × {48k, 96k} の Chrome 側は 48k (n=1) のみ | #187 |
| `asio_ramp_b128_d2` の FAIL (quick, 負荷起因の疑い) | 回帰判定の不安定さ | #187 (要切り分け) |
| 30 分ソーク (AU-10 null-sink 版) | 長時間の underrun 0 が未確認 | #187 |
| 実機の outputLatency・総往復遅延・Safari | CI で測れない | [AU-22] (#2366) |

## 5. Firefox 行列 (AU-23 #2540・WebDriver BiDi)

- **測定 commit**: `7c94bec0` (コードを変えた最後の commit。初版 `bbfe9795` の後に `--extra` を追加し、行列を `7c94bec0` で測り直した)。
  コード差分の確認: `git diff 7c94bec0 HEAD -- tools/audio/harness tools/audio/au2_matrix.sh tools/audio/au2_summary.mjs tools/audio/build.sh tools/audio/src tools/audio/test`
- **環境**: ubuntu runner (4 vCPU)・Firefox 157.0 (`--headless`, `MOZ_HEADLESS=1`)・PulseAudio 16.1 (apt 導入)・既定 sink = `module-null-sink sink_name=ci_null`・emsdk は `toolchain-emsdk` (`tools/audio/build.sh` 15 s)。
- **駆動**: `harness/bidi.mjs` (`withFirefox`: `chrome.mjs` の `serve` を共用し、`{navigate, eval}` は `withChrome` と同形。評価は `script.evaluate` + `awaitPromise`)、`harness/au2.mjs` (1 rep で 48k・96k を 1 セッション実行、再生中に `pactl list short sink-inputs` を 300 ms 間隔で採取)。
- **再現**: `bash tools/audio/au2_matrix.sh 3` → `results/au2/firefox_r{1,2,3}.json`、集計 `node tools/audio/au2_summary.mjs`。条件は B=256・depth=2・sine・10 s。48k は `asio_sine_b256_d2`、96k は `asio_sine_b256_96k` と同名 (`harness/run.mjs`)。
- **PASS の判定**: `run.mjs` の `underrunFree` と `sineOk` に加え、`ctx.sampleRate` が要求値に一致し、abort と worklet エラーが無いこと。

### 5-1 行列 (n=3)

| browser | sampleRate | シナリオ | n | PASS | underruns | burst (f) | T (f) | clock (Hz) | baseLatency (s) | outputLatency (s) | sink-input が ci_null に接続 | sink-input の規格 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| firefox | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 1024–1152 | 1536–1792 | 48010–48017 | 0 | 0.04825–0.04908 | 3/3 | float32le 2ch 48000Hz |
| firefox | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 1920 | 2816 | 96021–96052 | 0 | 0.04832–0.04903 | 3/3 | float32le 2ch 96000Hz |

- 行列全体 85.8 s (1 rep 約 28.5 s、各 rep 開始時の load avg 0.16–0.27)。sine の最大誤差は 6 run すべて 1.49e-8、`zero_runs_ge16=0`。`ctx.sampleRate` は 6 run すべて要求値と一致。
- 参考 (§1、Chrome 48k n=1、PulseAudio 起動時): burst 1152・T 1792・baseLatency 0.011625 s・outputLatency 0.036 s。Firefox の報告値は baseLatency が 0 (未実装扱いとして記録)、outputLatency が約 0.048 s。

### 5-2 Firefox の制約 (受入 4・probe を各 rep 1 回、計 3 回)

| 項目 | 実測 (Firefox 157.0) | 判定 |
|---|---|---|
| SharedArrayBuffer / crossOriginIsolated | `function` / `true` (3/3) | 成り立つ |
| main thread の `Atomics.wait(…, 0)` | TypeError (3/3) | 成り立つ (main では wait 不可) |
| AudioWorklet 内 `Atomics.wait(…, timeout 20 ms)` | `timed-out`、経過 19–21 ms (3/3) | **成り立たない**: Firefox は worklet での wait を止めず、実際にブロックする |
| AudioWorklet 内 `Atomics.notify` | `function` (3/3) | 成り立つ |

- 「worklet は notify のみ」は Firefox では強制されない。ただし `public/worklets/fl-audio-worklet.js` は `Atomics.notify` (3 箇所) しか使わず wait を呼ばないため、shim の動作はこの制約の成否に依らない。
- 行列の 6 run がすべて underrun 0 で通ったことも、worklet が Firefox で正常に動いている証跡になる。Chrome・Safari の worklet は未測定 (範囲外)。

### 5-3 ネガティブコントロール (各 n=1)

| NC | 操作 | 期待 | 実測 |
|---|---|---|---|
| 強制 underrun | `au2.mjs --rep 1 --extra "hiccup_ms=60&hiccup_every=200"` | 両条件 FAIL・終了コード非 0 | 0/2 PASS・rc=1。48k は underruns=8・silence=7296f、96k は underruns=16・silence=30592f (`results/au2/neg/hiccup_r1.json`) |
| sink 接続 | 既定 sink を別の null-sink `ci_other` に変えて実行 (`--secs 4`) | sink-input の `ci_null` 接続が false | 音声判定は両条件 PASS (`ci_other` へ出力)。`on_ci_null=false` が両条件 (`results/au2/neg/sink_other_r1.json`)。接続判定は実際に区別できる |

### 5-4 検証範囲 / 範囲外

- **範囲**: Firefox 157.0 headless (Linux)・PulseAudio null-sink (既定 sink)・48k/96k・sine・B=256・depth=2・10 s・n=3。
- **範囲外**: Chrome 96k (未測定)・Safari・実機 outputLatency ([AU-22])・30 分ソーク・負荷下・Firefox の他版。
- **sink の規格**: 測定中に固定していない。起動直後は `s16le 2ch 44100Hz`、測定後は `s16le 2ch 48000Hz` を観測した。sink-input の規格は Firefox の要求どおり 48000/96000 Hz。PulseAudio が sink 側へ再サンプルしたかは未確認 (`clock` は AudioContext 側の値)。

### 5-5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Chrome の 96k 行が未測定。Chrome の sink-input 接続も未確認 (§1) | 行列の Chrome 側が 48k (n=1) のみで、接続の裏付けが無い | #187 |
| sink の規格固定と PulseAudio 再サンプルの有無 | 96k の clock が sink 経路で変わるかは未確定 | #187 |
| Firefox 他版・Safari・30 分ソーク・負荷下 | 版差・長時間・負荷下の未確認 | #187 / [AU-22] (#2366) |
