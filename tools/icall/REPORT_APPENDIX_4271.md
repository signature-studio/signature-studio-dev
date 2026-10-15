# REPORT_APPENDIX_4271 — Fresh Air closure に callee を加えて missing function abort を減らす (ICALL-96)

親: #1886 (ICALL-89) / 子 (残件): #4328 (ICALL-99)。前提: `REPORT_APPENDIX_1633.md` (closure 151 関数)・`REPORT_APPENDIX_1838.md` (CHAININFO 伸長)。

## 結論

- `missing function` の abort は 0 件になった (修正前 7 件 → 測定 commit `181e26ebd` で 0 件)。
- ただし issue の前提「15 件が closure に含まれない」は、測定時点で一部しか成り立たない。`fa_ranges_1633.txt` (151 関数) には 15 件の開始 VA がすべて入っていた。RetDec の after 段で `func_map` に入ったのは 5 件。残り 10 件は範囲に入るが関数として取り込まれず、`missing function` は closure の拡張だけでは消えない (未解決は #4328)。
- 修正前 (131 関数) に wasm のみ err だった 7 関数 (0x1803b5500・0x1803fb6f0・0x18040c950・0x180ca1480・0x180da5f20・0x181057d20・0x18106632c) は、closure 拡張後に bit 一致へ変わった (両 sweep.jsonl の突き合わせ・共通 131 関数で判定が変わったのはこの 7 件のみ)。
- 0x18082ecf0 は closure 拡張後に新たに `missing function` になった callee。root に加えて 152 関数で解消した。

## 1. 入力 (測定 commit `181e26ebd`)

- 範囲: `tools/icall/fa_ranges_4271.txt` (152 関数)。作成: `fa_ranges_1633.txt` (151) の範囲を CHAININFO 伸長 (`prep_targets.ranges_with_ends`, chained=True) で作り、closure (`closure.py`) の root に `0x18082ecf0` を加えた。
- 素材: `plugins-freshair` の `SlateCore.core_64` (36,285,952 B)、`work-icall` (展開不要: 旧 `rt_freshair-core` は使わず、本 run で roundtrip を再実行)。
- コード変更: `tools/icall/fa_route_build.sh` と `tools/icall/diff/fa_sweep.sh` に `FA_MAP` (map.json の差し替え) を追加。既定値は従来どおり `rt_freshair-core/map.json`。

## 2. 実測 (測定 commit `181e26ebd`)

| 項目 | 結果 |
|---|---|
| roundtrip (`roundtrip.sh`) | 38.2 s・rc 0。`rewrote 141 funcs`・`call total=137`・`lost 6` (非IAT)。`ir_call_dir_total` 2 → 2 |
| `fa_route_build.sh` (`FA_SRC`・`FA_MAP` 指定) | 9.5 s・OK |
| `fa_sweep.sh 8 60` | 75 s・`funcs 142 | bit一致 66 | native crash/timeout 72 | wasm のみ err 2 | 値の不一致 2` |
| `missing function` の件数 | 0 件 |
| `libottnative.so` | `tools/ott/native/build.sh` で先にビルド (0.4 s) |

### 修正前との比較 (同じ sweep の既定入力 = 131 関数、`FA_MAP` 無し・`fa_ranges_1633.txt`。この行は本 run の実測で、測定 commit は `e9a8ff66b`〜`181e26ebd` のどれでも既定入力の挙動は同じ (`git diff e9a8ff66b 181e26ebd -- tools/icall` は `FA_MAP` の追加と範囲ファイルの追加のみ))

| 区分 | 修正前 (131 関数) | 修正後 (142 関数・`181e26ebd`) |
|---|---|---|
| bit 一致 | 55 | 66 |
| wasm のみ err | 9 | 2 |
| 値の不一致 | 2 | 2 |
| `missing function` | 7 | 0 |

注: 修正前の 131 関数の sweep は、本 run の `FA_MAP` 無し (既定値) で実行した。issue 本文の「修正前 bit 一致 56 / wasm のみ err 9 / 値の不一致 1」とは 1 件ずれる (値の不一致 2)。本 run の数値を正とする。

### 残った wasm のみ err / 値の不一致 4 件

| VA | 結果 | 分類 |
|---|---|---|
| 0x1803dee20 | 値の不一致 (8/8) | 本 issue の範囲外。追跡先 #4348 (ICALL-101) |
| 0x180da4030 | 値の不一致 (8/8) | 正の確定は既存の #4291 (ICALL-98) |
| 0x180c8b280 | bit 一致 6・`memory access out of bounds` 2 | 別原因。追跡先 #4349 (ICALL-102) |
| 0x181057b38 | `memory access out of bounds` 8 | 別原因。追跡先 #4349 (ICALL-102) |

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 15 件中 10 件 (0x1803b5546・0x18040ca0d・0x1808299a6・0x180829caa・0x180c98030・0x180c982ca・0x180c995ac・0x180ca1651・0x180da6084・0x180da6850) が after 段で `func_map` に入らない。before dsm では直前が `data inside code section` と出る | 範囲には入るが関数として lift されず、呼び出し元の sweep で `missing function` の余地が残る (現測定では 0 件) | #4328 (ICALL-99) |
| 0x1803dee20 の値の不一致 (8/8) | bit 一致を妨げる | #4348 (ICALL-101) |
| 0x180da4030 の値の不一致 (8/8) | bit 一致を妨げる | #4291 (ICALL-98) |
| 0x180c8b280・0x181057b38 の out-of-bounds | 別原因 | #4349 (ICALL-102) |

## 4. 再現

```
bash tools/ott/native/build.sh
PE="tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
bash tools/icall/roundtrip.sh "$PE" tools/icall/fa_ranges_4271.txt freshair-4271
FA_SRC=tools/icall/work/rt_freshair-4271/after.0.restored.ll FA_MAP=tools/icall/work/rt_freshair-4271/map.json bash tools/icall/fa_route_build.sh
FA_MAP=tools/icall/work/rt_freshair-4271/map.json bash tools/icall/diff/fa_sweep.sh 8 60
```

前提: `plugins-freshair` を `fetch.sh` で展開済み、`toolchain-retdec`・`toolchain-emsdk`・`work-icall`・`work-liftlib` が有る。

## 5. 測定 commit 以降の差分 (受入条件 3)

測定 commit: `181e26ebd` (コードを変えた最後の commit)。その後の REPORT 更新は `85a29daea` (付録の追加) と、本 fix の commit。

`git diff 181e26ebd HEAD -- tools/icall` の stat (`85a29daea` 時点):

```
 tools/icall/REPORT_APPENDIX_4271.md | 66 +++++++++++++++++++++++++++++++++++++
 1 file changed, 66 insertions(+)
```

- 差分の 66 行はすべて本付録自身 (`REPORT_APPENDIX_4271.md`) の追加。付録の本文を diff として貼ると、貼った時点で付録自身の内容がずれるため、stat で代えた。
- `tools/icall` のコード差分 (`fa_ranges_4271.txt`・`fa_route_build.sh`・`diff/fa_sweep.sh`) は `git diff 181e26ebd HEAD -- tools/icall/fa_ranges_4271.txt tools/icall/fa_route_build.sh tools/icall/diff/fa_sweep.sh` が 0 行。測定の入力は変わっていない。

## 6. 既知の注意 (未対応)

- `fa_ranges_4271.txt` に重複・重なる範囲がある (例: `0x180c9d700-0x180c9d880` と `0x180c9d880-0x180c9da15`、`0x180da68a8-0x180da68b3` と `0x180da6850-0x180da68b3`)。測定入力を変えないために今回は整理していない。範囲の整理は #4328 (ICALL-99) で、入力を変える測定と同時に行う。
