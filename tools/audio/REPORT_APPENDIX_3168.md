# AU-33 (#3168) Firefox 行列の OS 別 sink 判定と 3 シナリオ化 — 検証の全文

親: `REPORT_AU2_CI.md` §11 (要点)。250 行上限のため分割移動。issue #3168 (親 #3164 / PR #3169)。

## A. 測定 commit と差分

- 測定 commit: `9aa9239b` (`feat(audio): Firefox 行列の既定出力判定を OS 別にし 3 シナリオへ揃える`)。Firefox 9/9 はこの commit のコードで測った。以後の本 PR の commit は REPORT・results・DOC_MAP の追加と修正だけで、コードは変えていない。ただし main の取り込み (merge `c9c45ea6`・`fa57175d`) で main 由来のコードが入った (下の (a)・(b))。
- 変更前 main: `1b37410c` (ベースライン測定の commit)。
- `git diff 9aa9239b HEAD -- tools/audio/harness tools/audio/au2_firefox_matrix.sh tools/audio/au2_firefox_summary.mjs` の出力: 測定 commit では 0 行。HEAD `c89f18db` では 3 ファイル (103 行追加・5 行削除。`harness/run.mjs`・`harness/safari.mjs`・`harness/safari_probe.mjs`。いずれも main 由来で、Firefox e2e は読まない)。
- (a) 実行コードの範囲 (build.sh の入力を含む): `git diff --stat 9aa9239b HEAD -- tools/audio/src tools/audio/harness tools/audio/test tools/audio/build.sh tools/audio/flags.sh tools/audio/au2_firefox_matrix.sh tools/audio/au2_firefox_summary.mjs public/worklets src/runtime` の出力: 測定 commit では 0 行。HEAD `c89f18db` では 8 ファイル (225 行追加・9 行削除)。`flags.sh` は build.sh が source する入力で、REPORT_AU2_CI.md §9 の列挙には無かったため足した。
  - Firefox e2e の入力 2 件: `public/worklets/fl-audio-worklet.js` (3 行)・`src/runtime/audio-shim.ts` (7 行)。build.sh が配置・コンパイルし、e2e が実行する。どちらも main の `7c5ee224` (AU-29 #3115) 由来。**この 2 件が変わったため、HEAD の Firefox 結果は 9aa9239b の 9/9 で代替できない**。HEAD `c89f18db` で再測定し 9/9 PASS (§G)。
  - Firefox e2e が読まない 6 件: `harness/run.mjs`・`harness/safari.mjs`・`harness/safari_probe.mjs`・`test/safari_mock_test.mjs`・`test/safaridriver_mock.mjs`・`test/worklet_jump_check.mjs` (main 由来)。`au2.mjs` → `bidi.mjs` → `chrome.mjs` の import 鎖に無く、build.sh も copy しない。
- (b) issue #3168 指定の範囲: `git diff --stat 9aa9239b HEAD -- tools/audio` の出力は 20 ファイル (5497 行追加・9 行削除。HEAD `c89f18db` に §G の記録を足した作業ツリーで取った値)。内訳は次の 2 種。
  - PR 自身の記録 10 件: `REPORT_APPENDIX_3168.md`・`REPORT_AU2_CI.md`・`results/au2_ff_ubuntu/` 下の JSON 8 件 (`firefox_r1`〜`r3`・`neg/*.json`・`base_main_1b37410c/firefox_r1`〜`r3`)。
  - main 由来 10 件: `REPORT_APPENDIX_3193.md`・`REPORT_AU29.md`・`au2_summary.mjs`・`ci/audio-matrix.yaml` と、上の (a) の Firefox e2e が読まない 6 件 (AU-29・AU-32・AU-35 の追加)。`au2_summary.mjs` (Chrome 行列 `au2_matrix.sh` の集計) と `ci/audio-matrix.yaml` (workflow 定義) は、Firefox e2e が実行しない。
- (c) HEAD での再測定: `c89f18db` で実施し 9/9 PASS (§G)。素材の `toolchain-emsdk` は本 run に無かったため、上流 emsdk 6.0.12 を runner 上に入れた。
- (b) の値は、この記録を含む作業ツリーで `git diff --stat 9aa9239b -- tools/audio` を取った値。記録ファイル自体も範囲に入るため、記録 commit のたびに動く。
- `git diff 1b37410c 9aa9239b -- tools/audio/harness tools/audio/au2_firefox_matrix.sh tools/audio/au2_firefox_summary.mjs` の変更: 4 ファイル、45 行追加・23 行削除 (`au2.mjs` 42 行・`bidi.mjs` 5 行・`au2_firefox_matrix.sh` 8 行・`au2_firefox_summary.mjs` 13 行)。

## B. 変更の中身

| ファイル | 変更 |
|---|---|
| `tools/audio/harness/au2.mjs` | 既定出力の判定を OS 別にした。Linux: 従来どおり PulseAudio の `ci_null` の sink-input を 300 ms 間隔で採る。Windows (`win32`): `powershell -Command "(Get-AudioDevice -Playback).Name"` が `CABLE Input` を含むこと (再生の前後の 2 回)。macOS (`darwin`): `SwitchAudioSource -c -t output` が `BlackHole 2ch` を含むこと (前後の 2 回)。per-stream の sink-input は Windows・macOS に相当情報が無いため、既定出力の名前で代える。シナリオを Chrome 行列 (`audio-matrix.yaml`) と同じ 3 本にした (`asio_sine_b512_96k` を追加)。出力キーは `pulse_sink_input.on_ci_null` から `sink_route.on_expected` に変え、`os`・`expected_sink` を足した |
| `tools/audio/harness/bidi.mjs` | `FIREFOX` 未指定時の既定の実行ファイルを OS 別にした (win32: `C:\Program Files\Mozilla Firefox\firefox.exe`、darwin: `/Applications/Firefox.app/Contents/MacOS/firefox`、他: `firefox`)。pactl への依存は無い (元から) |
| `tools/audio/au2_firefox_matrix.sh` | 出力先を `AU2_OUT` で変えられるようにした (既定 `results/au2`・`au2_matrix.sh` と同じ)。この script は Linux 専用 (PulseAudio の起動を含む) |
| `tools/audio/au2_firefox_summary.mjs` | 第 1 引数で結果ディレクトリを読む。旧キー (`pulse_sink_input`・`on_ci_null`) も読む |

## C. ubuntu での再現 (受入 1 の ubuntu 部分・測定 commit `9aa9239b` の記録)

- 注: 下の表と `results/au2_ff_ubuntu/firefox_r*.json` の 9aa9239b 時点の値は、§G の HEAD 再測定で JSON が上書きされた。9aa9239b の値は git 履歴に残る。
- 環境: ubuntu runner (4 vCPU)、Firefox 157.0 (headless)、PulseAudio 16.1 (apt 導入。`module-null-sink sink_name=ci_null` を既定 sink)、emsdk は `toolchain-emsdk` を `$RUNNER_TEMP` に展開 (`EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh`)。`bash tools/audio/build.sh` は 15.2 s で成功。
- 再現コマンド: `AU2_OUT=tools/audio/results/au2_ff_ubuntu bash tools/audio/au2_firefox_matrix.sh 3` (終了 0)。wall 41.0 s / 40.5 s / 40.6 s、load (1 分値) 開始 0.22 / 0.18 / 0.36、終了 0.18 / 0.36 / 0.26。
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
| 強制 underrun | `au2.mjs --rep 1 --secs 4 --extra "hiccup_ms=60&hiccup_every=200"` | 両方 FAIL・rc≠0 | **0/3 PASS**・rc=1。underrun 3 / 7 / 3・silence 3968〜21120 f・`on_expected=true` (`neg/hiccup_r1.json`) |

## E. Safari (macOS) と Windows / macOS (未検証)

- **Safari**: 経路は #3208 (AU-35 #3193) で main に入った (merge `83060945`・2026-10-14T23:51:51Z・`harness/safari.mjs`)。測定 commit `9aa9239b` の時点では経路が無かった。理由 (測定時): (1) この runner は Linux で Safari を起動できず、P1〜P4 を実測できない。(2) harness は Chrome CDP (`chrome.mjs`) と Firefox WebDriver BiDi (`bidi.mjs`) の 2 経路のみだった。(3) Safari が WebDriver BiDi に対応するかは本 run で未確認 `[未確認]`。
- **代替案**: macOS runner で `safaridriver` (WebDriver classic) から `au2.mjs` 相当を駆動する経路。`safaridriver --enable` と Safari の remote automation 許可が要る `[未確認: 手順は macOS 実機で確認]`。既定出力の判定は darwin 分岐 (`BlackHole 2ch`) を使う。実装は #3208 で main に入った。残りの macOS 実測の起票先: #3207 [AU-36] (`REPORT_APPENDIX_3193.md` が正本)。
- **Windows / macOS の Firefox 行**: `audio-matrix.yaml` は #3169 (branch `3164-au32-win-mac-audio-matrix`、merge `ac7ad1c6`・2026-10-14T23:27:19Z) で main に入った (origin/main の yaml は 100 行)。前提の #3169 merge は満たされている。Safari 行 (`browser: safari`) は #3208 で入ったが、Firefox 行はまだ無い (yaml に `firefox` の記述が 0 件)。Firefox 行の追加は #3192 [AU-34] で行う。追加する内容: matrix に `os: windows-latest / browser: firefox / firefox: 'C:\Program Files\Mozilla Firefox\firefox.exe'` と `os: macos-latest / browser: firefox / firefox: '/Applications/Firefox.app/Contents/MacOS/firefox'` を足し、`measure` の step で `browser == firefox` の行は `node tools/audio/harness/au2.mjs --rep $rep --out audio-results/...` を呼ぶ (`FIREFOX` env を渡す)。Chrome 行は従来どおり `run.mjs`。
- **未検証**: `win32`・`darwin` の判定分岐 (PowerShell の `Get-AudioDevice`・`SwitchAudioSource`) は Linux runner では実行していない。`node --check` 通過のみ。dispatch 結果は適用後に記録する (起票先 #3192 [AU-34])。

## F. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Windows / macOS の Firefox 行 (yaml) は main に未適用 (#3169 は merge 済み)。Win/mac の dispatch 結果なし | 受入 1 の Win/mac は未達 | #3192 [AU-34] (Firefox 行の適用と dispatch を行い、§10 に記録) |
| `win32`・`darwin` の判定分岐は未実行 | 判定の実機確認が無い | #3192 [AU-34] (dispatch の結果で確かめる) |
| Safari (macOS) の P1〜P4 | 未測定 (経路は #3208 で main 入り) | #3207 [AU-36] (`REPORT_APPENDIX_3193.md` が正本) |

## G. HEAD `c89f18db` の再測定 (Firefox 9/9・受入 1 の HEAD 部分)

- 測定 HEAD: `c89f18db`。実行コード (§A (a) の範囲) は PR の検証 HEAD と同じ。この記録 commit で変わるのは REPORT・results の追加だけ。
- 環境: Linux runner、Firefox 157.0 (headless・`/usr/bin/firefox`)、PulseAudio (apt の `pulseaudio`・`pulseaudio-utils` を導入。`module-null-sink sink_name=ci_null` を既定 sink)、emsdk 6.0.12 (`tools/m1/flags.sh` の pin。上流 `emsdk install 6.0.12` を `$RUNNER_TEMP/emsdk` に入れ、`EMSDK_ENV` で指定。`toolchain-emsdk` 素材は本 run に無い)、`node_modules` は main 作業ツリーのものを symlink (build.sh が使うのは `tsc` のみ)。
- 手順と結果: `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh bash tools/audio/build.sh` が成功。続けて `AU2_OUT=tools/audio/results/au2_ff_ubuntu bash tools/audio/au2_firefox_matrix.sh 3` を foreground で実行し **rc 0** (2 分 28 秒)。
- wall (rep 1〜3): 66.0 / 40.5 / 40.6 s。load (1 分値) の開始 0.62 / 0.43 / 0.67、終了 0.43 / 0.67 / 1.79。rep 1 の wall が長い原因は未確認。
- 結果: **9/9 PASS** (3 rep × 3 シナリオ・underrun 0・sine 誤差 1.49e-8・zeroRuns 0・`ctx.sampleRate` 一致・worklet エラー 0・既定 sink 接続 9/9)。集計 (`node tools/audio/au2_firefox_summary.mjs tools/audio/results/au2_ff_ubuntu`):

| browser | sampleRate | シナリオ | n | PASS | underruns | burst (f) | T (f) | clock (Hz) | baseLatency (s) | outputLatency (s) | 既定出力 (期待 sink) に接続 | sink-input の規格 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| firefox | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 1024–2304 | 1536–3328 | 47997–48018 | 0 | 0.0481875–0.049166666 | 3/3 | float32le 2ch 48000Hz |
| firefox | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 1920 | 2816 | 96004–96010 | 0 | 0.04915625–0.04921875 | 3/3 | float32le 2ch 96000Hz |
| firefox | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 1920 | 3072 | 95994–96027 | 0 | 0.049145833–0.04925 | 3/3 | float32le 2ch 96000Hz |

- 所見: 48k の burst・T は rep 1 が 2304・3328、rep 2・3 が 1024・1536 で、run ごとに揺れる (§C の所見と同じ種類)。96k は 3 rep とも同値。
- §A (a) の実行コード範囲は `c89f18db` でも 8 ファイル・225 行追加・9 行削除 (`fa57175d` と同じ)。
- NC (§D) は HEAD では再実行していない (9aa9239b の値)。

