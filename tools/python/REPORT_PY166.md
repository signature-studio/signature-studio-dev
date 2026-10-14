# tools/python REPORT: PY-166 (#3176) flrack.rack の属性表の PE 確定 (loop_starter_config の型・書込み可否)

> 正本: `tools/python/REPORT_PY22.md` §4.1・§5 (flrack の mock 一覧と未解決)。本付録は PY-166 の PE 実測のみ。

## 結論

- 親 #3176 の受入条件 4 件は 1 run で全て満たせなかった。範囲を「`flrack.Rack` の属性表の PE 確定」に縮め、残りを子 #3181 (`flrack.flr`・PY-167) と #3182 (src 反映と e2e 再測定・PY-168) に分けた。
- PyMemberDef 形式として読んだ場合、`flrack.rack.loop_starter_config` は **`T_OBJECT_EX`** (型番号 16)・**書込み可** (flags 0)。CPython の T_OBJECT_EX は未設定 (NULL) の読出しで AttributeError を出す。この読みは「表が PyMemberDef 形式である」という前提に依存する。全行の offset が 0 である理由は未確定で、前提の成否は未解決表 (子 #3182) に残す。
- 同梱 pyc (`block24774_DATA.bin`) では `loop_starter_config` (offset 18804) と `AttributeError` (offset 18856) の名前が近接して現れる。例外処理の構造は未確認のため、これと AttributeError の対応は推定。
- PE は値の型を課さない。同梱 pyc の名前列 (`dumps` (offset 18784)・`loads` (offset 18849)) から、Python 側が JSON 文字列として代入し、読むときは `json.loads` で取り出すと推定する (推定。実 FL の実値は未確認)。
- 既定値の mock `{"mock": true, ...}` は mock (根拠なし)。PyMemberDef 前提で PE の表から読めるのは「型は任意の object・未設定なら AttributeError」までで、実 FL の既定値は未確定。
- `flrack.flr` は `flrack.Rack` の属性表に無い。型・戻り値は未確定 (子 #3181)。

## 手段

- 解析補助: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flrack_rack_probe.py [属性名 ...]` (本 PR で追加)。PE (`extracted/block00031_PE.bin`) の属性名の char* を指す qword を .data 上で探し、その 40 byte 行 (`name`・`type`・`offset`・`flags`・`doc`) の前後を名前 0 の終端まで読む。
- 型番号は CPython の `PyMemberDef` の `T_*` に対応させた (`0x01` T_INT・`0x03` T_FLOAT・`0x0e` T_BOOL・`0x10` T_OBJECT_EX)。
- 名前文字列 `loop_starter_config` は VA `0xd33b99` (`.text` 内)。これを指す行は VA `0x1513d58`。
- `flrack.Rack` 型の記述子 `0x1513e48` を参照するのは 2 箇所 (`pe_xref.py`・33.3 秒・命令 5,022,467 件を走査): `0xd33ded` (`lea rdx`) と `0xd3667f` (`lea rcx`、モジュール初期化の 1 回フラグ `0x983a7d` の内側で、3 型の登録呼出し `0x415c30` の 3 件目)。

## 属性表 (`flrack.Rack`、PE 行 `0x1513ba0`〜`0x1513da8`)

| name | type | 意味 (PyMemberDef の T_*) | flags | 備考 |
|---|---|---|---|---|
| channels | 0x10 | T_OBJECT_EX | 0x1 | 読取専用の可能性 (READONLY 相当) |
| pattern_id | 0x01 | T_INT | 0 | |
| rack_initialised | 0x0e | T_BOOL | 0 | |
| PPS | 0x01 | T_INT | 0 | |
| BPM | 0x01 | T_INT | 0 | |
| sample_rate | 0x01 | T_INT | 0 | |
| pattern_length | 0x01 | T_INT | 0 | |
| genre | 0x10 | T_OBJECT_EX | 0 | |
| swing | 0x03 | T_FLOAT | 0 | |
| pattern_scale_root | 0x01 | T_INT | 0 | |
| pattern_scale_helper | 0x10 | T_OBJECT_EX | 0 | |
| **loop_starter_config** | **0x10** | **T_OBJECT_EX** | **0** | PyMemberDef 前提で書込み可 |
| pattern_scale_is_set | 0x01 | T_INT | 0 | |
| pattern_scale_name | 0x10 | T_OBJECT_EX | 0 | |

- 表の根拠 (属性表と型記述子の対応): 型記述子 `0x1513e48` の先頭 qword は `flrack.Rack` の名前ポインタ (VA `0xd33be4`)。`+0x18` は `0x1513df8` を指し、その記録の `+0x8` は表の先頭 `0x1513ba0` を指す。記録の件数欄 `0x40` と表の 14 行の対応は未確認。
- 全行の `offset` は 0。PyMemberDef なら行ごとに構造体内の位置が入るはずで、全行 0 の理由は未確定。このため型・書込み可の読みは前提付き。格納先 (インスタンス内の位置) は表からは読めない。T_OBJECT_EX の getter / setter 本体は未特定。
- `flr` の名前は表に無い。`flr\0` の文字列は PE に 0 件。

## 未確定 (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 全行 offset 0 の理由 (表が PyMemberDef 形式か・格納先) | T_OBJECT_EX・書込み可の読みは前提付き | 子 #3182 (PY-168) |
| `loop_starter_config` の getter / setter 本体 (T_OBJECT_EX の分岐と既定 NULL の扱い) | 未設定時の AttributeError は CPython の T_OBJECT_EX の仕様からの推定 | 子 #3182 (PY-168) |
| `loop_starter_config` の値の型 (JSON 文字列か) | mock の JSON 文字列は mock (根拠なし)。同梱 pyc からの推定 | 子 #3182 (PY-168) |
| `flrack.flr` の型・戻り値 | 既存の `flrack.flr = types.SimpleNamespace()` は mock (根拠なし)。`tools/python/tests/chord_progression_call_probe.mjs:69-70`・`chord_progression_e2e.mjs:76-77` にあり、本 probe にはない | 子 #3181 (PY-167) |
| src/ 反映と `chord_progression_e2e.mjs` の HEAD 再測定 (41/41・--neg FAIL 7) | 本 PR は wasm を再ビルドしていない | 子 #3182 (PY-168) |
| 実 FL 照合 (mock 値と実値の一致) | 未確認。親の起票先 #81 (PY-9) は閉鎖済みのため、追跡を #3182 にコメントで移した | 子 #3182 (PY-168) |

## 検証

測定 commit: `b472af91` (probe に `T_BOOL` を追加した commit。コードを変えた最後の commit)。以後の commit は本 REPORT の文言だけを変える。`git diff b472af91 HEAD -- tools/python/analysis/flapi/pe_flrack_rack_probe.py` の出力は 0 行。`pe_xref.py` は本 PR で変更していない。

| コマンド | 結果 | wall |
|---|---|---|
| `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先>` | rc 0・`extracted/block00031_PE.bin` 22,227,016 byte | 7.574 秒 (user 2.040 秒・sys 4.679 秒) |
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flrack_rack_probe.py` (`b472af91`) | rc 0・出力 15 行 (見出し 1 + 表 14 行)・`loop_starter_config` の行 `0x1513d58`・`rack_initialised` は T_BOOL | 0.220 秒 (user 0.212 秒・1 分 load 0.51) |
| 同 (ネガティブコントロール: 属性名 `no_such_attr`) | rc 0・出力 0 行。存在しない名前に行を出さない。ただし rc は 0 のままで、失敗は rc では検出されない | 0.032 秒 |
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_xref.py 1513d58,1513e48` (`b472af91`) | rc 0・`hits=2` (`0xd33ded`・`0xd3667f`)・命令 5,022,467 件 | 33.3 秒 (user 33.0 秒・1 分 load 0.47)。別 run (レビュー時・`ca9dcec3`) は 60.8 秒 |

## 再現

```
FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi/pe_flrack_rack_probe.py
```

`<fl-win64 展開先>` は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先>` で得る (`extracted/block00031_PE.bin` が要る)。
