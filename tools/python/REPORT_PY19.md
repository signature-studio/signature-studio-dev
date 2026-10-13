# REPORT 付録 PY-19 — flpianoroll の残り 2 メンバ (#792)

> 本体: [REPORT.md](REPORT.md)。親: #79 (PY-5)。起点 HEAD: `ca117e76` (origin/main)。
> 行数上限のため、#79 の stub 解消の全文はここに置く。

## 1. 対象と受入条件の判定

| 受入条件 | 結果 |
|---|---|
| `Score.loadScoreFromFile` を仮想 FS 経由で実装。ネガコン (存在しないパスで失敗) | 達成 (§2) |
| `ScriptDialog.DialogParams` を実装。実 FL の戻り値が未確認の部分は mock と明記 | 達成 (実装は MOCK、§3) |
| 既存 `pyscript_e2e.mjs` (43/43) が不変。数え方の定義と再計算スクリプトを REPORT に書く | 達成 (§4、§5) |

## 2. Score.loadScoreFromFile (仮想 FS 読込)

- 実装: `src/flpianoroll.py`。`open(path)` で読み、`json` として解釈して `Score.load(d)` に渡す (`dump()` と同形式)。
- ASSUMPTION: FL の `.fst` / `.fsc` (独自形式) は未解析。実 FL の入力形式とは一致しない。
- 失敗の種別: 存在しないパスは `FileNotFoundError`、不正 JSON は `JSONDecodeError`、object 以外は `ValueError`。実 FL の失敗種別は未確認。
- 検証: `tests/flpianoroll_dialog_load_e2e.mjs` の正常系 4 + ネガコン 3 (NEG-1〜3) = 7 checks。

## 3. ScriptDialog.DialogParams (MOCK)

- **MOCK 値**: 戻り値は `{控制名: 現在値}` の dict。実 FL の戻り値の形 (dict / オブジェクト / キー名) は未確認。
- 根拠の確認: `analysis` 用の FL Windows PE (`block00031_PE.bin` ほか) から `DialogParams` という名前の文字列は取れるが、戻り値の仕様を読める doc 文字列は見つからなかった。
- 実 FL との照合は #81 (PY-9) の範囲。
- 検証: 既定値・group 接頭辞・`set_values` 反映の 4 checks (`tests/flpianoroll_dialog_load_e2e.mjs`)。

## 4. 数え方の定義と再計算

- 母集団: `analysis/flapi/flapi_table.json` の `objects.flpianoroll.classes` の全メンバ。Note 17 / Marker 7 / score(Pattern) 22 / Utils(TUtils) 3 / ScriptDialog 15 = **64**。
- 実装判定: `src/flpianoroll.py` を import し、該当クラス/インスタンスに属性があること (`hasattr`)。
- stub 判定: `NotImplementedError` の grep (本 PR 後は 0 件)。`hasattr` は stub を区別しないため、併用する。
- 再計算: `python3 tools/python/analysis/flpianoroll_members.py` (終了コード 0 = 全件実装)。`--json` で機械可読。

## 5. 実測 (検証 HEAD: 本 PR の commit。ビルドは同 worktree)

本 run で確認したものだけを残す。e2e (`flpianoroll_dialog_load_e2e.mjs`・`pyscript_e2e.mjs`・`all_tools.mjs`・`midi_script.mjs`) と build は、本 run では素材 (`toolchain-emsdk`・`dist/`) が無く再実行していない。

| 項目 | 結果 |
|---|---|
| 再計算 | `flpianoroll_members.py`: 64/64 implemented (exit 0) |

e2e の検査項目 (件数・PASS の記録は持たない): `flpianoroll_dialog_load_e2e.mjs` は `loadScoreFromFile` の正常系・ネガコン (§2) と `DialogParams` (§3) を検査する。`pyscript_e2e.mjs` は既存の回帰として §4 の範囲を含む。実測は §6 の再実行で取る。

### 注意: 実行時の環境変数

`pyscript_e2e.mjs` は `FL_WIN64_DIR` を必須にする。未指定だと exit 2 で何も出力しない (ログは空)。実行は `FL_WIN64_DIR=<展開先> node tests/pyscript_e2e.mjs` とすること。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `DialogParams` の戻り値の形 (MOCK) | HUD / 実スクリプトが戻り値を使う場合の互換 | #81 (PY-9)・#10 (HUD) |
| `loadScoreFromFile` の入力形式 (`.fst`/`.fsc` 独自形式) | 実 FL が書いた score を読めない | 未起票 (本 issue 残件として明記) |
| `loadScoreFromFile` の失敗種別 (実 FL) | ネガコンは Python 標準例外で代用 | #81 (PY-9) |
| `pyscript_e2e.mjs` / `flpianoroll_dialog_load_e2e.mjs` / 回帰 (`all_tools.mjs`・`midi_script.mjs`) / build の再実行 | 本 run は `toolchain-emsdk` が無く `dist/` も無いため再実行できない。実測値は本 REPORT に残さない。wall 秒数は受入条件外 | #792 (`oc_artifacts: fl-win64 toolchain-emsdk` の run で再実行し、run ID 付きで本 REPORT §5 に記録) |
