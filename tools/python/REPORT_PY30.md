# PY-30 (#1327): flcpt.cpt の 4 メンバの根拠確定と実装

結論: **部分達成** (スコープを縮小)。CPT の 4 メンバ (`addChordMarker` / `getChordMarker` / `clearChordMarkers` / `chordMarkerCount`) は FLEngine PE の実装から引数の書式・int 戻り値・要素返却・内部配列の操作を確定し、`src/flcpt.py` に実装した。None の戻り値は推定のまま (同定は #3034)。ただし probe の呼べた数は **3/9 のまま増えなかった** (残りは ChordMarker 側の未確定属性)。`resolution`・ChordMarker/ChordAlternative・`chordPool`・`flrack` は根拠未確定のため、子 issue に分割した (§5)。

## 1. 入力と前提

| 項目 | 手順 | 実測 |
|---|---|---|
| fl-win64 展開 | `tar --zstd -xf fl-win64.tar.zst` (`$RUNNER_TEMP/fl-win64`) | 成功 (7 s) |
| FLEngine PE | `extracted/block00031_PE.bin` | 22,227,016 B |
| CPython wasm | `bash build_cpython_wasm.sh` | exit 0 (2 分 45 秒) |
| emsdk | runner 同梱の emsdk (emcc 6.0.12) を使用 | toolchain-emsdk artifact は未展開 (不要だった) |
| pyc 抽出 | `analysis/extract_pyc_blocks.py work/fl_extract` | pyc 40 本・pyscript 2 本 |
| flpy 再リンク | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | exit 0 (追跡の `flapi_table.json` は不変) |

FL 由来物は `work/` (gitignore) に置き、commit しない。

## 2. 根拠 (FLEngine PE の CPT 表と各ハンドラ)

CPT の表は `flapi_table.json` の `CPT` 列 (addChordMarker / getChordMarker / clearChordMarkers / chordMarkerCount) と名前が一致し、同じ `.data` 領域 (0x1513008〜0x15130af) にある。

| メンバ | 表の entry | fn | flags | 引数 (書式) | 戻り値 | 呼出し (実測の逆アセンブル) |
|---|---|---|---|---|---|---|
| `addChordMarker` | PyMethodDef `0x1513008` | `0xd2edd0` | 1 (VARARGS) | `PyArg_ParseTuple` 書式 `'O'` (`0xd2ee24`) → 1 個の任意オブジェクト | 成功時は `0xc38bc0` の戻り値 (**None と推定**・§2.3)。引数解析失敗時は NULL | 内部配列の末尾へ追加 `0x50a830` |
| `getChordMarker` | PyMethodDef `0x1513028` | `0xd2ee50` | 1 (VARARGS) | 書式 `'i'` (`0xd2eec4`) → int32 index | `index < 0` または `index >= count` なら `0xc38bc0` の戻り値 (**None と推定**)。それ以外は要素 | `0x50aa70(list, index)` で添字参照 |
| `clearChordMarkers` | PyMethodDef `0x1513048` | `0xd2eed0` | 4 (NOARGS) | なし | `0xc38bc0` の戻り値 (**None と推定**) | `count > 0` の間、`0x50aa70(list,0)` で取得し `0x50a8c0(list,0)` で先頭を削除 |
| `chordMarkerCount` | getset `0x1513088` (name, get=`0xd2ee30`, set=0, doc=0) | `0xd2ee30` | — (読取専用) | なし | `int` (32bit の要素数を `PyLong_FromLong` で返す) | `mov ecx,[list+0x10]` → `call` slot `0x15e4280` |

- 内部配列: `self+0x10` が内部配列のヘッダ。`+0x8` が要素配列、`+0x10` が要素数 (count)。`0x50a830` は `items[count]=obj; count++`、`0x50a8c0` は添字 index の要素を取り除いて後続を詰める。
- 間接呼出しの同定 (既存の確定事項を流用): slot `0x15e1e58` = `PyArg_ParseTuple` (REPORT_PY152 §44)、slot `0x15e4280` = `PyLong_FromLong` (REPORT_PY152 §42)。
- 未同定: `addChordMarker`・`getChordMarker`・`clearChordMarkers` の参照カウント操作 (slot `0x15e33c0`・`0x15e3...` 系)。Python 実装では対応する効果を持たせていない (Python の参照で代替)。
- 戻り値 None の根拠は §2.3 (推定のみ。確定していない)。

### 2.1 再現

```
FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi/pe_handler_probe.py addChordMarker getChordMarker clearChordMarkers chordMarkerCount
```

表の entry・fn・flags と逆アセンブル (引数の書式 `lea rdx,[rip+X]` の文字列 `'O'`・`'i'`) が出る。`chordMarkerCount` の getset の名前は `pe_handler_probe.py` が同じ表から引く。

### 2.2 所属の根拠の限界

`flcpt.CPT` の型名文字列 (`0xd2f228`) を指す .data 0x1513138 は PyTypeObject の位置として読んだが、`tp_methods`・`tp_getset` の直接参照は確認できなかった (0x1513120 からの配列が PyTypeObject の形にならなかった)。所属は「名前一致 + 同じ表領域 + 内部配列の操作」で判断した。

### 2.3 戻り値 None の推定 (未確定)

- `0xc38bc0` は `mov rax,[rip+0xa7f719]; ret` (逆アセンブル実測)。戻り値は `[0x16b82e0]` の値である (`0xc38bc7 + 0xa7f719 = 0x16b82e0`)。
- `0x16b82e0` は `.bss` (`SizeOfRawData` 0・file 実体なし)。値は実行時にしか決まらないため、静的には `None` (Py_None) と確定できない。
- 3 つのハンドラは `call 0xc38bc0` の戻り値をそのまま返す (`addChordMarker` 0xd2ee16 → 0xd2ee1b、`getChordMarker` 範囲外 0xd2ee90 → 0xd2ee95 → 0xd2eeb6、`clearChordMarkers` 0xd2ef07 → 0xd2ef0c の ret)。rax は上書きしていない。
- 既存の `REPORT_PY73.md` は同じ `0xc38bc0` を『Py_None と推定、未実測』とし、`REPORT_PY123.md` は `[0x16b82e0]` を『静的には決まらない』と結論している。
- よって表と実装の `None` は **推定**。同定は #3034 [PY-141] の範囲。

## 3. 実装 (`src/flcpt.py`・`build_flpy.sh`)

- `src/flcpt.py` (新規): `CPT` クラス (要素は Python list)。4 メンバは §2 の表どおり (None 戻り値は推定・§2.3)。`cpt = CPT()` を module 属性として置く。
- `ChordMarker` / `ChordAlternative` / `ChordPool` は import 時に名前を参照されるだけの空の型。**mock (根拠なし)**。
- `build_flpy.sh`: `src/flcpt.py` を `fl/Lib` に入れる 1 行を追加。
- `tests/chord_progression_e2e.mjs`: `flcpt` の空スタブを `import flcpt` (実装) に置換。`flcpt.chordPool` は mock のまま (SimpleNamespace)。
- `tests/chord_progression_call_probe.mjs`: `flcpt.cpt` を `_CPTRec` (実装 + 未確定属性だけ `Rec` に委譲) に置換。各呼出しの前に `clearChordMarkers()` で状態を初期化 (行ごとに独立させるため。実装は状態を持つ)。

未確定の属性 (`resolution`・`genre`・`chordPool` の全属性・`flrack` 全体) は引き続き mock (根拠なし)。実 FL 照合は #81 (PY-9)。

## 4. 検証 (変更前 → 変更後)

| 項目 | 変更前 (`1f31671^` = `e9881327`) | 変更後 (`1f31671`) |
|---|---|---|
| `node tests/chord_progression_e2e.mjs` | 41/41 PASS (0.3 s) | 41/41 PASS (0.3 s) |
| `node tests/chord_progression_e2e.mjs --neg` | 34/41・FAIL 7・exit 1 | 34/41・FAIL 7・exit 1 |
| `node tests/chord_progression_call_probe.mjs` (呼べた数) | 3/9 | **3/9 (増えなかった)** |

測定 commit (列ごと):

- 変更前の列: `1f31671^` = `e9881327` (PR の base。コードを変える直前の commit)。この列は PR 作成時の測定値で、本 REPORT の追記時には再測定していない (この runner に emsdk が無く wasm を作れないため)。
- 変更後の列: `1f31671` (コードを変えた最後の commit)。この commit で再現した。
- `git diff 1f31671 HEAD -- tools/python/src tools/python/tests tools/python/build_flpy.sh` の出力は `src/flcpt.py` の module docstring の 4 行 (`-` 4 行・`+` 4 行。戻り値の記述を推定に直した行) だけ。実行されるコードは変わらない: `compile()` した `co_code` は 1f31671 と HEAD で一致し、AST は module docstring を除いて一致する。`tests`・`build_flpy.sh` の差分は 0。

### 4.1 呼び出し表 (probe)

変更前 (`e9881327`・スタブ: 全属性を Rec が記録):

| 関数 | 結果 | 読まれた flcpt 属性 |
|---|---|---|
| apply_chord_preset | OK | cpt.chordMarkerCount, cpt.resolution |
| get_chord_name | AttributeError: 'list' object has no attribute 'split' | - |
| text_to_chord | StopIteration | cpt.addChordMarker, cpt.chordMarkerCount |
| get_chord_root | TypeError: '<=' int と Rec | cpt.getChordMarker, .time |
| get_chord_preset_str | OK | cpt.chordMarkerCount |
| get_rhythm_preset_str | IndexError | cpt.chordMarkerCount |
| get_chord_pool_preset_str | NotImplementedError | - |
| analyse_chord | StopIteration | cpt.chordMarkerCount |
| reset | OK | chordPool.clear, cpt.clearChordMarkers, cpt.genre |

変更後 (`src/flcpt.py` の CPT 4 メンバ + 行ごとの初期化):

| 関数 | 結果 | 読まれた flcpt 属性 (Rec に委譲された分のみ) |
|---|---|---|
| apply_chord_preset | OK | cpt.resolution |
| get_chord_name | AttributeError: 'list' object has no attribute 'split' | - |
| text_to_chord | AttributeError: 'ChordMarker' object has no attribute 'alternativeCount' | - |
| get_chord_root | TypeError: '<=' int と str | - |
| get_chord_preset_str | OK | - |
| get_rhythm_preset_str | IndexError | - |
| get_chord_pool_preset_str | NotImplementedError | - |
| analyse_chord | StopIteration | - |
| reset | OK | chordPool.clear, cpt.genre |

集計: 9 関数中、呼べた 3 (変更前と同じ)。変化は失敗理由のみ。`text_to_chord` は `addChordMarker` を通過し、次は ChordMarker 側の `alternativeCount` で止まる。`get_chord_root` の比較相手が Rec から str に変わったが、原因の追跡は未実施。

注: 変更後の表は行ごとに初期化した結果。変更前の表は状態を持たないスタブ。`apply_chord_preset` の「OK」は `chordMarkerCount` が 0 の早期 return (変更前と同じ)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `CPT.resolution`・`chordPool`・`genre` (apply_chord_preset / reset が読む) の根拠と実装 | apply_chord_preset の実処理 (要素あり側) と reset の後半が未検証 | #3174 (PY-164) |
| `ChordMarker` / `ChordAlternative` の属性 (`time`・`alternativeCount` ほか) の根拠と実装 | text_to_chord・get_chord_root・reset が呼べない。**呼べた数が増えない原因** | #3175 (PY-165) |
| `flrack` の型・戻り値 (rack.loop_starter_config・flr 等) | flrack 依存の関数の戻り値は mock (根拠なし) | #3176 (PY-166) |
| `addChordMarker`・`getChordMarker`・`clearChordMarkers` の戻り値 None (`0xc38bc0` = `[0x16b82e0]` の値) | None は推定 (§2.3)。mock と同じ扱い | #3034 (PY-141) 既存 |
| 実 FL の戻り値照合 | mock 値と実値の一致は未確認 | #81 (PY-9) 既存 |
| `flcpt.CPT` の PyTypeObject からの tp_methods / tp_getset の直接参照 | §2.2 の所属根拠が間接的 | 未起票 (本節に記載のみ) |

## 6. 再現

```
bash build_cpython_wasm.sh                                    # 2 分 45 秒
FL_WIN64_DIR=<fl-win64 展開先>/extracted "$PY312" analysis/extract_pyc_blocks.py work/fl_extract
FLPY_SKIP_TABLE=1 FL_WIN64_DIR=<fl-win64 展開先> bash build_flpy.sh
node tests/chord_progression_e2e.mjs                          # 41/41
node tests/chord_progression_e2e.mjs --neg                    # 34/41 (exit 1)
node tests/chord_progression_call_probe.mjs                   # 呼べた 3/9
```
