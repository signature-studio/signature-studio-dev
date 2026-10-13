# REPORT 付録 PY-23 — enveditor と Audio scripts 12 本の import / 実行検証 (#1054)

**結論**: `enveditor` の Edison API を実装し、同梱 Audio scripts **12/12** が wasm CPython 上で import・実行できる。
回帰 `tests/pyscript_e2e.mjs` は **56/56 PASS** (うちネガティブコントロール 4)。
12 本のうち 6 本は独立 oracle と数値照合、残り 6 本 (`br` `dest` `lim` `rm` `pulse` `saw`) は実行完了のみ確認。
実 FL の戻り値・挙動との照合は未実施 (下記 §未解決)。

## 1. 仕様の出典

- `enveditor` の仕様は FL 同梱の **Edison Script Reference** (`fl-win64` の `extracted/block24447_DATA.bin`)。
  `flapi_table.json` には `enveditor` が無いため、メンバ表はこの文書から起こした (`src/enveditor.py` 冒頭参照)。
- 対象の使用メンバは 12 本の静的集計による: `Editor.SelectionStartS/EndS`・`EditorSample` 系 (`GetSampleAt` `SetSampleAt` `AmpFromTo` `SilenceFromTo` `SineFromTo` `PasteFromTo` `NormalizeFormat` `MSToSamples` `Length` `SampleRate` `NumChans` `RegionCount` `GetRegion` 等)・`Sample()`・`Utils.ProgressMsg`・`ScriptDialog`。

## 2. 実装

| 項目 | 内容 |
|---|---|
| `src/enveditor.py` | `Sample` / `Region` / `TEditor` (Editor) / `TUtils` (Utils)。`EditorSample` `Editor` `Utils` は module 変数。`reset(sample, selection)` `dump()` `install()` |
| `src/fl_rt.py` | `run_audio(name, sample, selection, values)` (createDialog → apply) と `load_audio(path, name, sample, selection)` (トップレベル実行の本用) を追加 |
| `build_flpy.sh` | `enveditor.py` を `fl/Lib/` に配置 |
| `tests/pyscript_scenarios.mjs` | 旧 "0/12 ModuleNotFoundError" 検査を、実行検証に置き換え |

戻り値・挙動の mock 値 (`mock (根拠なし)`。実 FL 照合は #81 (PY-9)。`# ASSUMPTION:` と同義):
- `Sample` の既定 `SampleRate=44100`・`NumChans=2`。
- `SineFromTo` の Phase はラジアン・`x1` を位相 0 の基準とする。
- `NoiseFromTo` の乱数源は Python `random` (実機の系列とは一致しない)。
- `LoadFromFile` / `LoadFromFile_Ask` は未対応 (`NotImplementedError`)。`LoadFromClipboard` はホスト注入なし時に空。
- サンプル形式 (ビット深度) は保持せず、`NF_Format` は no-op。

## 3. 12 本の結果

| # | 本 (ScriptDialog 題名) | 実行 | 検証 |
|---|---|---|---|
| 1 | Amp | PASS | 独立 oracle: 選択 [2,5] のみ ×0.5 |
| 2 | Bit reduction | PASS | 実行完了のみ |
| 3 | Destructoid | PASS | 実行完了のみ |
| 4 | Limiter | PASS | 実行完了のみ |
| 5 | Old school | PASS | 独立 oracle: SampleRate=11000・8bit 量子化 |
| 6 | Ring modulation | PASS | 実行完了のみ (clipboard mock が空のため変化なしの想定) |
| 7 | Pulse generator | PASS | 実行完了のみ |
| 8 | Saw generator | PASS | 実行完了のみ |
| 9 | Silence generator | PASS | 独立 oracle: Length 100 の無音 |
| 10 | Sine generator | PASS | 独立 oracle: 44100 samples・選択内が 1000Hz 正弦 |
| 11 | Region 変換 (トップレベル) | PASS | 独立 oracle: SampleEnd = 次 Start、末尾は Length-1 |
| 12 | Play To End (トップレベル) | PASS | 独立 oracle: 既定 (No/No) で全 region の SampleEnd = Length-1 |

12 本すべて `load` が通る (`enveditor` の import 解決)。

## 4. ネガティブコントロール

| 名 | 改変 | 結果 |
|---|---|---|
| NEG-d | Amp の `AmpFromTo(x1,x2,value)` → `value*2` | 改変版 `mg[2]` ≠ 0.25 を検出 → PASS (FAIL を検出) |

受入条件の「pyc 先頭 1 バイト反転」は、Audio scripts が `.pyscript` (ソース) のため**そのままは適用できない**。
代わりにソースの適用量を改変した (NEG-d)。ソース先頭バイトの反転は未実施。

## 5. 実測 (コミット済み HEAD)

- 測定 commit: `37269b91` (`feat(python): enveditor module ... (Refs #1054)`)。
- `node tests/pyscript_e2e.mjs`: **0.96 秒 (wall)**、56/56 PASS、FAIL 0。node v22.23.3、4 core、load average 0.25 / 0.40 / 0.43。
- `node tests/flpianoroll_dialog_load_e2e.mjs`: 0.27 秒 (wall)、11/11 PASS。
- `python3 analysis/flpianoroll_members.py`: 64/64 implemented (exit 0)。
- `git diff 37269b91 HEAD -- tools/python/src tools/python/tests tools/python/build_flpy.sh` の出力は 0 行 (測定後にコード変更なし)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FL (Edison) の `EditorSample` 各メンバの戻り値・境界挙動 (`NormalizeFromTo`・`PasteFromTo` の mode 挙動・`Length` setter 等) | mock 値のため実機と異なる可能性 | #81 (PY-9) |
| `br` `dest` `lim` `rm` `pulse` `saw` は実行完了のみ (数値 oracle 未実装) | 数値の正しさは未検証 | #1310 (PY-28) |
| ソース先頭 1 バイト反転のネガティブコントロール | 受入条件の文言 (pyc) と不一致 | #1310 (PY-28) |
| Chrome (headless) 上の Audio 実行 (本検証は node のみ) | §7 で解決 (#1323 / PY-29) | #1323 (解決済み) |

## 6. 残り (子 issue)

受入条件のうち「6 本の数値 oracle」と「先頭 1 バイト反転のネガコン」は本 run では未達。
子 issue **#1310 [PY-28]** に起票済み (OPEN)。上の未解決表の 2 行目・3 行目がこれに対応する。

## 7. Chrome (headless) 上の Audio 12 本の実行検証 (#1323 / PY-29)

既存の Chrome 版ハーネス (`tests/pyscript_browser.mjs` + `tests/pyscript_scenarios.mjs`、PY-11 / #466) が Audio 12 本も同一シナリオで実行する。本 run ではハーネスを変えずに、Audio 12 本の実行と node 版との一致を確認した。

- 測定 commit: `18e9910b` (main 取り込み済み・コード変更なし)。
- 手順 (HEAD で再現): `FL_WIN64_DIR=<fl-win64> bash build_cpython_wasm.sh` → `bash fetch_inputs.sh` → `bash build_flpy.sh` → `node tests/pyscript_e2e.mjs --dump work/pyscript_node.json --export-scripts work/pyscripts.json` → `node tests/pyscript_browser.mjs --dump work/pyscript_chrome.json` → `python3 tests/pyscript_compare.py work/pyscript_node.json work/pyscript_chrome.json`。
- ブラウザ: Chrome 154.0.0.0 headless、agent-browser 0.39.0、`crossOriginIsolated=true`。node v22.23.3。runner 4 core。

| 回 | load average (1 分, 開始時) | node (56 check) | Chrome (56 check, スクリプト内 / wall) | compare |
|---|---|---|---|---|
| 1 | 0.40 | 56/56 PASS, 1.2 s wall | 56/56 PASS, 1.4 s / 2.3 s wall | checks 56/56, outputs 19 件 不一致 0, exit 0 |
| 2 | 0.40 | 56/56 PASS, 1.2 s wall | 56/56 PASS, 1.4 s / 2.3 s wall | 同上 |
| 3 | 0.45 | 56/56 PASS, 1.2 s wall | 56/56 PASS, 1.4 s / 2.3 s wall | 同上 |

- Audio 12 本の内訳 (node / Chrome とも同一): load 12/12 PASS。独立 oracle 6 本 (Amp・Old school・Silence generator・Sine generator・Region 変換・Play To End) PASS。残り 6 本 (`br` `dest` `lim` `rm` `pulse` `saw`) は実行完了のみ PASS。NEG-d (Amp の適用量改変) は両環境で FAIL を検出。
- 差分: check 名・ok は node と Chrome で全件一致 (差分 0)。Audio 関連 check は 15 件 (node 15/15、Chrome 15/15)。
- 実行時の異常: 初回の Chrome 実行で `serve.mjs` の stderr が親から継承され、パイプが閉じずに止まった (500 秒超で打ち切り。残存プロセスは PID 指定で停止)。以後は `timeout` 付き・ログファイル出力で実行し、再現しなかった。ハーネスは未修正。
- 検証範囲: Chrome は mock engine (`host/fl_mock.mjs`) 上の実行。実 FL (Edison) との照合は #81 (PY-9)。
- git diff (測定 commit → HEAD、コード範囲): `git diff 18e9910b HEAD -- tools/python/src tools/python/tests tools/python/build_flpy.sh` は 0 行。

## 8. PY-28 (#1310): 残り 6 本の数値 oracle とネガティブコントロール

- 数値 oracle を追加: `br` (半偶数丸め・選択 [1,4])、`dest` (mix 0.75 / mix 1・rate 8000)、`rm` (clip 3 点で切詰め・Oversample 0/1・clipboard 空)、`pulse` / `saw` (Phase 0.3・0 から生成・44100 samples・倍音和)、`lim` (振幅 0.7/0.3/0.02 で max・通常・無音の 3 分岐を通す。Envelope No/Yes)。JS で手導出 (`lim` は Lookahead / Smoothing を写した JS 再実装を独立 oracle とする)。
- `rm` の clipboard は `enveditor.set_clipboard()` (新規ホスト hook。`src/enveditor.py`) で注入する。従来は未注入で空だった。
- ネガティブコントロール (対象 6 本それぞれ): (1) 先頭 1 バイト反転 → load が SyntaxError で FAIL を検出、(2) 適用量改変 (例 `vol*0.5`→`vol*0.25`、`v2 = gain`→`gain*1.01`) → oracle 不一致で FAIL を検出。
- 旧 "実行完了のみ" 6 本は、数値 oracle の検査へ置き換えた。

### 実測 (コミット済み HEAD)

- 測定 commit: `9d597acc` (`test(python): numeric oracles and negative controls for br/dest/lim/rm/pulse/saw (Refs #1310)`)。
- `node tests/pyscript_e2e.mjs`: **2.2 秒 (wall)**、72/72 PASS、FAIL 0 (変更前は 56/56・1.0 秒)。node v22.23.3、4 core、load average 0.46 / 0.28 / 0.35。
- `node tests/flpianoroll_dialog_load_e2e.mjs`: 11/11 PASS、FAIL 0。
- `python3 analysis/flpianoroll_members.py`: exit 0。
- `git diff 9d597acc HEAD -- tools/python/src tools/python/tests tools/python/build_flpy.sh` の出力は 0 行 (測定後にコード変更なし)。
