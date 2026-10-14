# tools/python REPORT: PY-166 (#3176) flrack.rack の属性表の PE 確定 (loop_starter_config の型・書込み可否)

> 正本: `tools/python/REPORT_PY22.md` §4.1・§5 (flrack の mock 一覧と未解決)。本付録は PY-166 の PE 実測のみ。

## 結論

- 親 #3176 の受入条件 4 件は 1 run で全て満たせなかった。範囲を「`flrack.Rack` の属性表の PE 確定」に縮め、残りを子 #3181 (`flrack.flr`・PY-167) と #3182 (src 反映と e2e 再測定・PY-168) に分けた。
- `flrack.rack.loop_starter_config` は FLEngine PE 上で **`T_OBJECT_EX`** (CPython `PyMemberDef` の型番号 16)・**書込み可** (flags 0)。CPython の T_OBJECT_EX は未設定 (NULL) の読出しで AttributeError を出すため、同梱 pyc (`block24774_DATA.bin`) の `try`/`except AttributeError` と整合する。
- PE は値の型を課さない。同梱 pyc の名前列 (`dumps`・`loads`・`AttributeError`) から、Python 側が JSON 文字列として代入し、読むときは `json.loads` で取り出すと推定する (推定。実 FL の実値は未確認)。
- 既定値の mock `{"mock": true, ...}` を実 FL の値とみなす根拠は無い。PE の表から読めるのは「型は任意の object・未設定なら AttributeError」までで、実 FL の既定値は未確定。
- `flrack.flr` は `flrack.Rack` の属性表に無い。型・戻り値は未確定 (子 #3181)。

## 手段

- 解析補助: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flrack_rack_probe.py [属性名 ...]` (本 PR で追加)。PE (`extracted/block00031_PE.bin`) の属性名の char* を指す qword を .data 上で探し、その 40 byte 行 (`name`・`type`・`offset`・`flags`・`doc`) の前後を名前 0 の終端まで読む。
- 型番号は CPython の `PyMemberDef` の `T_*` に対応させた (`0x01` T_INT・`0x03` T_FLOAT・`0x0e` T_BOOL・`0x10` T_OBJECT_EX)。
- 名前文字列 `loop_starter_config` は VA `0xd33b99` (`.text` 内)。これを指す行は VA `0x1513d58`。
- `flrack.Rack` 型の記述子 `0x1513e48` を参照するのは 2 箇所 (`pe_xref.py`・150 秒・命令 5,022,467 件を走査): `0xd33ded` (`lea rdx`) と `0xd3667f` (`lea rcx`、モジュール初期化の 1 回フラグ `0x983a7d` の内側で、3 型の登録呼出し `0x415c30` の 3 件目)。

## 確定した属性表 (`flrack.Rack`、PE 行 `0x1513ba0`〜`0x1513da8`)

| name | type | 意味 (CPython T_*) | flags | 備考 |
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
| **loop_starter_config** | **0x10** | **T_OBJECT_EX** | **0** | 書込み可 |
| pattern_scale_is_set | 0x01 | T_INT | 0 | |
| pattern_scale_name | 0x10 | T_OBJECT_EX | 0 | |

- 全行の `offset` は 0。格納先 (インスタンス内の位置) は表からは読めない。T_OBJECT_EX の getter / setter 本体は未特定。
- `flr` の名前は表に無い。`flr\0` の文字列は PE に 0 件。

## 未確定 (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `loop_starter_config` の getter / setter 本体 (T_OBJECT_EX の分岐と既定 NULL の扱い) | 未設定時の AttributeError は CPython の T_OBJECT_EX の仕様からの推定 | 子 #3182 (PY-168) |
| `loop_starter_config` の値の型 (JSON 文字列か) | mock の JSON 文字列は同梱 pyc からの推定 | 子 #3182 (PY-168) |
| `flrack.flr` の型・戻り値 | probe の `flrack.flr` mock (空の SimpleNamespace) は根拠なし | 子 #3181 (PY-167) |
| src/ 反映と `chord_progression_e2e.mjs` の HEAD 再測定 (41/41・--neg FAIL 7) | 本 PR では wasm を再ビルドしていない | 子 #3182 (PY-168) |
| 実 FL 照合 | mock 値と実値の一致は未確認 | #81 (PY-9) |

## 検証

測定 commit: `2ecab288` (probe と本 REPORT を含む。コードを変えた最後の commit)。以後の commit は本 REPORT の文言だけを変える。`git diff 2ecab288 HEAD -- tools/python/analysis/flapi/pe_flrack_rack_probe.py` の出力は 0 行。

| コマンド | 結果 | wall |
|---|---|---|
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flrack_rack_probe.py` (`2ecab288`) | rc 0・出力 15 行 (見出し 1 + 表 14 行)・`loop_starter_config` の行 `0x1513d58` | 0.382 秒 (user 0.372 秒・1 分 load 0.17) |
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_xref.py 1513d58,1513e48` (参照元確認) | `0xd33ded`・`0xd3667f` の 2 件 | 62 秒 (前述) |

## 再現

```
FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi/pe_flrack_rack_probe.py
```

`<fl-win64 展開先>` は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先>` で得る (`extracted/block00031_PE.bin` が要る)。
