# AU-33 (#3168) Firefox 行列の OS 別 sink 判定と 3 シナリオ化 — 検証の全文

親: `REPORT_AU2_CI.md` §11 (要点)。250 行上限のため分割移動。issue #3168 (親 #3164 / PR #3169)。

## A. 測定 commit と差分

- 測定 commit: `9aa9239b` (`feat(audio): Firefox 行列の既定出力判定を OS 別にし 3 シナリオへ揃える`)。以後は REPORT と `results/` の追加だけで、コードは変えていない。
- 変更前 main: `1b37410c` (ベースライン測定の commit)。
- `git diff 9aa9239b HEAD -- tools/audio/harness tools/audio/au2_firefox_matrix.sh tools/audio/au2_firefox_summary.mjs` の出力: 空 (0 行)。
- `git diff 1b37410c 9aa9239b -- tools/audio/harness tools/audio/au2_firefox_matrix.sh tools/audio/au2_firefox_summary.mjs` の変更: 4 ファイル、45 行追加・23 行削除 (`au2.mjs` 42 行・`bidi.mjs` 5 行・`au2_firefox_matrix.sh` 8 行・`au2_firefox_summary.mjs` 13 行)。

## B. 変更の中身

| ファイル | 変更 |
|---|---|
| `tools/audio/harness/au2.mjs` | 既定出力の判定を OS 別にした。Linux: 従来どおり PulseAudio の `ci_null` の sink-input を 300 ms 間隔で採る。Windows (`win32`): `powershell -Command "(Get-AudioDevice -Playback).Name"` が `CABLE Input` を含むこと (再生の前後の 2 回)。macOS (`darwin`): `SwitchAudioSource -c -t output` が `BlackHole 2ch` を含むこと (前後の 2 回)。per-stream の sink-input は Windows・macOS に相当情報が無いため、既定出力の名前で代える。シナリオを Chrome 行列 (`audio-matrix.yaml`) と同じ 3 本にした (`asio_sine_b512_96k` を追加)。出力キーは `pulse_sink_input.on_ci_null` から `sink_route.on_expected` に変え、`os`・`expected_sink` を足した |
| `tools/audio/harness/bidi.mjs` | `FIREFOX` 未指定時の既定の実行ファイルを OS 別にした (win32: `C:\Program Files\Mozilla Firefox\firefox.exe`、darwin: `/Applications/Firefox.app/Contents/MacOS/firefox`、他: `firefox`)。pactl への依存は無い (元から) |
| `tools/audio/au2_firefox_matrix.sh` | 出力先を `AU2_OUT` で変えられるようにした (既定 `results/au2`・`au2_matrix.sh` と同じ)。この script は Linux 専用 (PulseAudio の起動を含む) |
| `tools/audio/au2_firefox_summary.mjs` | 第 1 引数で結果ディレクトリを読む。旧キー (`pulse_sink_input`・`on_ci_null`) も読む |

## C. ubuntu での再現 (受入 1 の ubuntu 部分)

- 環境: ubuntu runner (4 vCPU)、Firefox 157.0 (headless)、PulseAudio 16.1 (apt 導入。`module-null-sink sink_name=ci_null` を既定 sink)、emsdk は `toolchain-emsdk` を `$RUNNER_TEMP` に展開 (`EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh`)。`bash tools/audio/build.sh` は 15.2 s で成功。
- 再現コマンド: `AU2_OUT=tools/audio/results/au2_ff_ubuntu bash tools/audio/au2_firefox_matrix.sh 3` (終了 0)。wall 41.0 s / 40.5 s / 40.6 s、load (1 分値) 開始 0.22 / 0.18 / 0.26、終了 0.18 / 0.36 / 0.26。
- 結果: **9/9 PASS** (3 rep × 3 シナリオ。underrun 0・sine 誤差 1.49e-8・zeroRuns 0・`ctx.sampleRate` 一致・worklet エラー 0・既定 sink 接続 3/3)。集計 (`node tools/audio/au2_firefox_summary.mjs tools/audio/results/au2_ff_ubuntu`):

| browser | sampleRate | シナリオ | n | PASS | underruns | burst (f) | T (f) | clock (Hz) | baseLatency (s) | outputLatency (s) | 既定出力に接続 | sink-input の規格 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| firefox | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 1024 | 1536 | 48003–48036 | 0 | 0.048583333–0.049104166 | 3/3 | float32le 2ch 48000Hz |
| firefox | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 1920 | 2816 | 95988–96018 | 0 | 0.049020833–0.049229166 | 3/3 | float32le 2ch 96000Hz |
| firefox | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 1920 | 3072 | 96000–96046 | 0 | 0.049239583–0.04928125 | 3/3 | float32le 2ch 96000Hz |

- 既存との比較 (`REPORT_AU2_CI.md` §9-1・測定 commit `63ea7d45`): 48k は burst 1024–1152・T 1536–1792 (§9-1)。今回は 1024・1536 (範囲に含まれる)。96k は burst 1920・T 2816 (§9-1 と同値)。clock は §9-1 の 96003–96016 に対し今回 95988–96018 (範囲が広がった)。outputLatency は §9-1 の 0.0283–0.049 に対し今回 0.0486–0.0493 (同じ上端)。
- 変更前 main (`1b37410c`) でも同じ harness を 3 rep 回した (`au2.mjs`・2 シナリオ・旧 sink 判定)。9/9 ではなく 6/6 PASS。48k の burst 1024–1792・T 1536–2560、96k の burst 1920・T 2816。結果は `results/au2_ff_ubuntu/base_main_1b37410c/` (集計: `node tools/audio/au2_firefox_summary.mjs tools/audio/results/au2_ff_ubuntu/base_main_1b37410c`)。
- 所見: 48k の burst・T は run ごとに揺れる (変更前の run は最大 1792・2560)。この揺れは sink 判定の変更とは別の量。`§9-4` の rep 1 の差と同じ種類。

## D. ネガティブコントロール (commit `9aa9239b`・各 n=1・rep 1・secs 4)

| NC | 操作 | 期待 | 実測 |
|---|---|---|---|
| 期待外れの sink | `pactl load-module module-null-sink sink_name=ci_other`・`set-default-sink ci_other` → `au2.mjs --rep 1 --secs 4` → `set-default-sink ci_null` | 両方 FAIL・rc≠0 | **0/3 PASS**・rc=1。3 シナリオとも `on_expected=false`・underrun 0・sine 誤差 1.49e-8 (音声は正しいが sink だけが外れる) (`neg/sink_other_r1.json`) |
| 強制 underrun | `au2.mjs --rep 1 --secs 4 --extra "hiccup_ms=60&hiccup_every=200"` | 両方 FAIL・rc≠0 | **0/3 PASS**・rc=1。underrun 3 / 7 / 3・silence 3840〜21120 f・`on_expected=true` (`neg/hiccup_r1.json`) |

## E. Safari (macOS) と Windows / macOS (未検証)

- **Safari**: 経路を作っていない。理由: (1) この runner は Linux で Safari を起動できず、P1〜P4 を実測できない。(2) 既存の harness は Chrome CDP (`chrome.mjs`) と Firefox WebDriver BiDi (`bidi.mjs`) の 2 経路のみで、Safari 用の経路が無い。(3) Safari が WebDriver BiDi に対応するかは本 run で未確認 `[未確認]`。
- **代替案 (未着手)**: macOS runner で `safaridriver` (WebDriver classic) から `au2.mjs` 相当を駆動する経路。`safaridriver --enable` と Safari の remote automation 許可が要る `[未確認: 手順は macOS 実機で確認]`。既定出力の判定は darwin 分岐 (`BlackHole 2ch`) を使う。起票先: #3193 [AU-35] (未着手のまま追跡)。
- **Windows / macOS の Firefox 行**: `audio-matrix.yaml` は PR #3169 (branch `3164-au32-win-mac-audio-matrix`) にのみ在り、main には無い。Firefox 行の追加は #3169 の merge 後に PM が行う。追加する内容: matrix に `os: windows-latest / browser: firefox / firefox: 'C:\Program Files\Mozilla Firefox\firefox.exe'` と `os: macos-latest / browser: firefox / firefox: '/Applications/Firefox.app/Contents/MacOS/firefox'` を足し、`measure` の step で `browser == firefox` の行は `node tools/audio/harness/au2.mjs --rep $rep --out audio-results/...` を呼ぶ (`FIREFOX` env を渡す)。Chrome 行は従来どおり `run.mjs`。
- **未検証**: `win32`・`darwin` の判定分岐 (PowerShell の `Get-AudioDevice`・`SwitchAudioSource`) は Linux runner では実行していない。`node --check` 通過のみ。dispatch 結果は適用後に記録する (起票先 #3192 [AU-34])。

## F. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Windows / macOS の Firefox 行 (yaml) は #3169 未 merge のため未適用。Win/mac の dispatch 結果なし | 受入 1 の Win/mac は未達 | #3192 [AU-34] (#3169 merge 後に PM が適用・dispatch し、§10 に記録) |
| `win32`・`darwin` の判定分岐は未実行 | 判定の実機確認が無い | #3192 [AU-34] (dispatch の結果で確かめる) |
| Safari (macOS) の P1〜P4 | 未測定。経路は未着手 | #3193 [AU-35] (代替案 E) |
