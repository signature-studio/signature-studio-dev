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
| `br` `dest` `lim` `rm` `pulse` `saw` は実行完了のみ (数値 oracle 未実装) | 数値の正しさは未検証 | 子 issue (下記 §6) |
| ソース先頭 1 バイト反転のネガティブコントロール | 受入条件の文言 (pyc) と不一致 | 子 issue (下記 §6) |

## 6. 残り (子 issue)

受入条件のうち「6 本の数値 oracle」と「先頭 1 バイト反転のネガコン」は本 run では未達。子 issue として起票する (番号は PR 本文・issue コメントに記載)。
| Chrome (headless) 上の Audio 実行 | node のみ | REPORT_CHROME (未実施) |
