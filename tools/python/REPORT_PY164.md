# PY-164 (#3174): flcpt.cpt の resolution・genre・chordPool の根拠確定 (部分達成)

結論: **部分達成**。根拠が取れたのは次の 3 点。
(1) CPT 属性表 (PE, 53 行) の型。`resolution` は T_FLOAT。
(2) `genre` は CPT 表に無い (`reset_chord_pool` の `hasattr` が偽になる根拠)。
(3) `chordPool` の名前は PE に無い (control.pyc の ImportError 経路で `None` になる根拠)。
値 (`resolution` の実値・getter) は FLEngine の実行時に決まり、表とハンドラからは確定できなかった。推定で埋めず、src/flcpt.py には属性を足していない。
mock の差し替えで probe の reset の読取りが変わった (§5)。呼べた数は 3/9 のまま。

## 0. 属性ごとの根拠

| 属性 | 根拠 (PE・pyc) | 確定した内容 | 未確定 |
|---|---|---|---|
| `cpt.resolution` | PE 属性表 行 `0x1512810` (§2) | 型 T_FLOAT (type 0x03) | 実値の getter・既定値 (§2.3) |
| `cpt.genre` | PE 属性表に無し。`'genre'` を指す qword は flrack.Rack 表の 1 件のみ (§2.2) | CPT の属性として存在しないと読める。`hasattr(flc,'genre')` は偽 (§4) | 表の完全性 (§6) |
| `chordPool` | PE に `chordPool` の文字列が無い (§3) | native flcpt に属性が無いと読める。control.pyc が `chordPool = None` (§3) | 実機での import 失敗の挙動 (§6) |
| `chordPool.clear` | 上の `chordPool` が None なら `None.clear` (§4) | 呼ばれる経路は genre の真偽と preset の真偽に依存 | 実機の経路 (§6) |

## 1. 入力と測定

| 項目 | 手順 | 結果 |
|---|---|---|
| fl-win64 展開 | `tar --zstd -xf fl-win64.tar.zst` | 成功 (7 s) |
| CPython wasm | `bash build_cpython_wasm.sh` | exit 0 (3 分 56 秒) |
| pyc 抽出 | `analysis/extract_pyc_blocks.py` (入力は `<展開先>/extracted`) | pyc 40 本・pyscript 2 本 |
| flpy | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | exit 0 |

測定 commit (コードを変えた最後の commit): `24f0421f1` (`test(python): flcpt の mock を ...`)。
変更前の列は `abf0981f7` (= PR の base。mock は旧版) で、この run で測定した。

| 測定 | 変更前 `abf0981f7` (旧 mock) | 変更後 `24f0421f1` |
|---|---|---|
| `node tests/chord_progression_e2e.mjs` | 41/41 PASS (0.6 s) | 41/41 PASS (0.5 s) |
| `node tests/chord_progression_e2e.mjs --neg` | 34/41・FAIL 7・exit 1 | 34/41・FAIL 7・exit 1 |
| `node tests/chord_progression_call_probe.mjs` (呼べた数) | 3/9 | 3/9 |
| probe の reset の読取り | `chordPool.clear`・`chordPool.clear()`・`cpt.genre` | 読取り 0 件 (OK) |

`git diff 24f0421f1 HEAD -- tools/python/src tools/python/tests` の出力は 0 行 (測定後の差分なし)。

### 1.1 probe の呼び出し表 (変更後)

| 関数 | 結果 | 読まれた flcpt 属性 |
|---|---|---|
| apply_chord_preset | OK | cpt.resolution |
| get_chord_name | AttributeError: 'list' object has no attribute 'split' | - |
| text_to_chord | AttributeError: 'ChordMarker' object has no attribute 'alternativeCount' | - |
| get_chord_root | TypeError: '<=' not supported between 'int' and 'str' | - |
| get_chord_preset_str | OK | - |
| get_rhythm_preset_str | IndexError | - |
| get_chord_pool_preset_str | NotImplementedError | - |
| analyse_chord | StopIteration | - |
| reset | OK | - |

集計: 9 関数中、呼べた 3 (変更前と同じ)。`apply_chord_preset` の「要素あり側」は、probe が要素を積まないため通っていない (ChordMarker の属性は #3175)。

## 2. FLEngine PE の CPT 属性表

解析: `analysis/flapi/pe_flcpt_cpt_probe.py` (`FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flcpt_cpt_probe.py resolution genre`)。
行の形式は `pe_flrack_rack_probe.py` と同じ PyMemberDef (name・type・offset・flags・doc の 40 byte)。型コードは REPORT_PY166 の対応 (0x01 T_INT・0x03 T_FLOAT・0x0e T_BOOL・0x10 T_OBJECT_EX)。

### 2.1 表 (53 行)

- 位置: `0x1512798`〜`0x1512fb8` (先頭 `style1`、末尾 `reference_octave`)。全行 offset 0・flags 0・doc なし。
- 型の内訳: T_INT 14・T_FLOAT 32・T_BOOL 7。
- `resolution` は行 `0x1512810`・T_FLOAT。`loop_length` は T_INT、`wrap_around` は T_BOOL。
- 表の名前は probe の出力 (53 行) が正本。REPORT には全行を写さない。

### 2.2 `genre` の所属

- `'genre'` の文字列 (`0xd33b65`) を指す qword は PE に 1 件だけで、行 `0x1513cb8` (flrack.Rack 表 `0x1513ba0`〜`0x1513da8`、14 行) にある。CPT の表には無い。
- したがって、FLEngine の CPT が `genre` を名前で公開する根拠は無い。

### 2.3 値と getter (未確定)

- 表の参照元は `.text` に無い (`.text` を 1 命令ずつ復号して `0x1512798`・`0x15130d0`・`0x15130e0`・`0x15130f8`・`0x1513120`・`0x1513008` を探し、RIP 相対参照は 0 件)。表は `.data` 上の絶対ポインタからだけ参照される。
- 表の行は offset 0 のため、値の格納先 (構造体の位置) は表からは読めない。値を読む関数 (getter) は未特定。
- `resolution` の実値は実行時に決まる。既定値は根拠が無いため定義しない。

## 3. chordPool の所属 (PE)

- `chordPool` の文字列は PE に 0 件 (ASCII・小文字・`ChordPool`・UTF-16LE・`chord_pool` を含む)。`ChordMarker` は 4 件、`ChordAlternative` は 1 件、`flcpt` は 4 件。
- したがって、native flcpt は `chordPool` を名前で公開しないと読める。

## 4. pyc 側の読み方 (control.pyc)

- module 先頭の import (offset 448〜476): `from flcpt import cpt, ChordMarker` → `flc` (native CPT)。続けて `from flcpt import chordPool`。
- 後者が ImportError のとき、except 節 (offset 6366〜6378) は `chordPool = _C` を実行する。`_C = None` は module offset 384〜386 で代入される。
- `flcpt_proxy` の import は別の節 (ModuleNotFoundError 節、offset 6408〜6436) にある。probe で `type(control.flc)` は注入した CPT で、proxy は使われていない (flcpt が読めるため)。
- `apply_chord_preset` (offset 1098〜1118): `int(flc.resolution)`。型は T_FLOAT (§2.1)。
- `reset` → `initialise_markers` → `reset_chord_pool` (co_names の連鎖):
  - offset 88〜152: `if hasattr(flc, 'genre'): genre = flc.genre` / `else: genre = ''`。genre が無いので `''`。
  - offset 164〜194: `genre` が偽のとき `chordPool.clear()`。chordPool が None なら AttributeError。
  - offset 398〜410: `preset` が真のときの 2 つ目の `chordPool.clear()`。

## 5. mock の差し替え (本 PR)

- `tests/chord_progression_call_probe.mjs`: `_CPTRec` は表 53 行の名前だけを Rec に委譲し、他は AttributeError (genre が `hasattr` で偽になる)。`flcpt.chordPool` の Rec を置かない。
- `tests/chord_progression_e2e.mjs`: `flcpt.chordPool` の SimpleNamespace を置かない (e2e は 41/41 のまま)。
- 結果: reset の読取りが 0 件になり、OK のまま。旧 mock では chordPool・genre を Rec で読んでいた。この run の probe の経路では、`chordPool.clear` (§4 の offset 164) に到達していない。到達しない理由は未確認。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `resolution` の getter と実値 | apply_chord_preset の数値経路は mock のまま | #3174 (本 issue を Refs で残す) |
| 表の完全性: 表は 53 行で、flapi_table.json の注記は「~70 attr」。表の外の属性の有無は未確認 | `genre` 不在の根拠は表の完全性に依存する | #3174 |
| chordPool の実機での扱い (ImportError → None → reset の経路) | FL 実機で reset が失敗するかは未確定。probe では到達していない | #81 (PY-9・実 FL 照合) 既存 |
| 要素あり側の apply_chord_preset と ChordMarker の属性 | probe の 3/9 が増えない原因 | #3175 (PY-165) 既存 |
| flrack の型と戻り値 | flrack 依存の関数は mock | #3176 (PY-166) 既存 |

## 7. 再現

```
cd tools/python
bash build_cpython_wasm.sh                                                            # 3 分 56 秒
FL_WIN64_DIR=<fl-win64 展開先>/extracted work/build-native/install/bin/python3.12 analysis/extract_pyc_blocks.py work/fl_extract
FLPY_SKIP_TABLE=1 FL_WIN64_DIR=<fl-win64 展開先> bash build_flpy.sh
FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi/pe_flcpt_cpt_probe.py resolution genre
node tests/chord_progression_e2e.mjs                                                  # 41/41
node tests/chord_progression_e2e.mjs --neg                                            # 34/41 (exit 1)
node tests/chord_progression_call_probe.mjs                                           # 呼べた 3/9
```
