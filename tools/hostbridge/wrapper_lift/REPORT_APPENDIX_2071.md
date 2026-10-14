# REPORT 付録 — #2071 (HB-H42): 引数型不一致 (`incompatible pointer types`) の判定と修復の再測定

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md` §12。本付録は #2071 の計測の全文。
> 結論 1 行: 引数の型不一致 1,245 + 1,251 件は全て呼出側の `L"..."` (wasm32 で 4B 単位) で、`--wide` で `(int16_t *)u"..."` に直すと 0 件になる。同じ原因の代入・初期化 (`int[N]` → `int16_t *`) 30 + 30 件も同じ方式で直し、残りは #1954 と #2853 の範囲。

測定 commit: `f70faf97` (`retdec_repair.py` の `--wide` を代入・初期化に広げた最後の commit)。
`f70faf97` より前の `retdec_batch.py`・`retdec_gotofix.py`・`emcc_per_function.py` は、`26f90ada` (main 取込み時点) から変えていない。raw C は `26f90ada` の `retdec_batch.py` で作った (下記)。
環境: `[RETDEC]` v5.0 (`toolchain-retdec`)・`[EMSDK]` 6.0.12 (`toolchain-emsdk`)・`fl-win64` (`$RUNNER_TEMP` に展開)。load average (1 分値) 0.3–1.1。

## 1. 手順と所要

1. `retdec_batch.py` (`KEEP_DIR` で raw C を残す・`26f90ada`): block19091 は 19,816 / 19,816 ok・RetDec 呼び出し 41 回・fail 0 (313.03 s)。block23676 は 19,826 / 19,826 ok・41 回・fail 0 (305.28 s)。
2. 修復前: `retdec_repair.py --int-ptr` → `retdec_gotofix.py` → `emcc_per_function.py`。
3. 修復後: `retdec_repair.py --wide --int-ptr` → `retdec_gotofix.py` → `emcc_per_function.py`。
4. 測定 commit `f70faf97` で 2・3 を再実行 (表 §3 の値)。

raw C・修復後 C は `$RUNNER_TEMP` に置き、commit しない。

## 2. 受入条件 1: 型不一致の原因の分類

修復前 (`--int-ptr` のみ、gotofix 後) の emcc error を、emcc の診断の型で数えた (block19091 / block23676):

| 種類 | block19091 | block23676 | 原因 (判定) |
|---|---|---|---|
| `incompatible pointer types passing 'int[N]' to parameter of type 'int16_t *'` | 1,245 | 1,251 | 呼出側の `L"..."` (全件)。宣言 `int16_t *` は正 (下記) |
| `incompatible pointer types assigning to / initializing 'int16_t *' from/with 'int[N]'` | 30 | 30 | 同じ `L"..."` を代入・初期化に渡している (全件) |
| `statement not in loop` | 27 | 27 | #1954 の範囲 (goto 化で残った分) |
| `use of undeclared label` | 16 | 16 | #1954 の範囲 |
| `assigning to 'struct structN' from incompatible type 'int64_t'` | 3 | 3 | #2853 の範囲 |
| 未宣言 identifier 2・member 参照 2・整数リテラル 1 | 5 | 5 | #2853 の範囲 |

- 1,245 + 30 件 (block19091) の全ての診断は `int[N]` (文字列リテラル) → `int16_t *`。RetDec の型推定や helper 宣言の型が原因の型不一致は 0 件 (修復後にこの種の診断は残らない)。
- 宣言側 `int16_t *` は正しい: 宣言先は IAT thunk 経由の Win32 API (`GetModuleHandleW`・`RegisterClipboardFormatW`・`RegQueryValueExW` は LPCWSTR)。判定の根拠と代表例は `REPORT_APPENDIX_1680.md` §2。
- 呼出側は wasm32 の `wchar_t` が 4B のため `L"..."` が 4B 単位になる。PE 内の文字列は UTF-16LE (2B 単位)。
- 今回追加した代入・初期化の 60 件 (block19091 30 件・block23676 30 件) は、`(int16_t *)u"..."` に直した literal を UTF-16LE にすると `block*_PE.bin` 内に存在することを確認した (60 / 60)。対象は、引数のみ直した版の出力との差分の行 (今回新たに直した行) に限った。

## 3. 受入条件 2・3: 修復前後の再測定 (測定 commit `f70faf97`)

| 項目 | block19091 修復前 | block19091 修復後 | block23676 修復前 | block23676 修復後 |
|---|---|---|---|---|
| 修復 | `--int-ptr` | `--wide --int-ptr` | `--int-ptr` | `--wide --int-ptr` |
| gotofix (`notloop` 78・`goto_replaced` 51・`label_inserted` 41) | 同 | 同 | 同 | 同 |
| `wide_widened` (直した `L"..."`) | — | 1,275 | — | 1,281 |
| `wide_skipped` | — | 0 | — | 0 |
| emcc exit 0 (41 ファイル中) | **3** | **23** | **3** | **23** |
| error 行 | 1,326 | **51** | 1,332 | **51** |
| 関数通過 (pdata 関数数中) | 18,967 / 19,816 | **19,779** / 19,816 | 18,974 / 19,826 | **19,789** / 19,826 |
| 関数 error (`functions_with_error`) | 846 | 34 | 849 | 34 |
| `unattributed_error_lines` / `failclosed_files` | 1 / 1 | 0 / 0 | 1 / 1 | 0 / 0 |
| emcc 合計所要 (`emcc_seconds_sum`) | 9.10 s | 10.34 s | 9.05 s | 10.28 s |

- 修復前 (`--int-ptr` のみ) の値は `REPORT_APPENDIX_1679.md` §3 の「修復 + goto 化」(測定 commit `98c5f8ca`) と一致する (1,326・18,967・3/41)。
- 修復後の残り 51 行 (両 block とも同一): `statement not in loop` 27・`use of undeclared label` 16 (#1954)・struct 代入 3・未宣言 identifier 2・member 参照 2・整数リテラル 1 (#2853)。
- 測定の再現: `retdec_repair.py --wide --int-ptr <raw> <rep>` → `retdec_gotofix.py <rep> <goto>` → `emcc_per_function.py <goto> --targets <fl-win64>/extracted/block19091_PE.bin --out <json>`。修復前は `--wide` を外す。

## 4. 引数のみ直した版との差 (参考)

| 版 | block19091 exit 0 / error 行 | block23676 exit 0 / error 行 | 内容 |
|---|---|---|---|
| 引数のみ `--wide` (`26f90ada` の `retdec_repair.py`) + gotofix | 17 / 81 | 17 / 81 | 引数 1,245 / 1,251 → 0。代入・初期化 30 件が残る |
| 代入・初期化を追加 (`f70faf97`) + gotofix | **23 / 51** | **23 / 51** | §3 の表 |

- 代入・初期化の 30 件は、診断の列が `L"` の位置を指さない (代入は `=`、初期化は変数名の位置) ため、引数版の列指定では直せなかった (`wide_skipped` 30)。`wide_at_size` で「診断の行にあり、要素数 `N` が一致する `L"..."` が一意にある場合だけ」直すようにして解消した (`wide_skipped` 0)。

## 5. 残り (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `statement not in loop` 27・`use of undeclared label` 16 (両 block) | emcc exit 0 が 41 件中 23 件 (残り 18 件の主因) | #1954 (HB-H41) |
| struct 代入 3・未宣言 identifier 2・member 参照 2・整数リテラル 1 (両 block) | 同上の残り 18 件に含まれる (原因未切り分け) | #2853 (HB-H47) |
| 修復後の wasm 実行 (bit 一致) | 修復の正しさ未検証 (`(int16_t *)u"..."` の値が RetDec の意図と一致するかは wasm 実行系が無いため未検証) | #829 (HB-H20) 系の実行検証 |

## 6. 未検証・注意

- `wide_at_size` は、診断の行に要素数 `N` が一致する `L"..."` が 1 つだけあるときに限って直す。同じ行に同じ要素数の `L"..."` が 2 つ以上ある場合は直さない (`wide_skipped` に入る)。今回は 0 件。
- `(int16_t *)u"..."` が RetDec の意図と一致するかは、wasm 実行系が無いため未検証 (修復前の `REPORT_APPENDIX_1680.md` §6 と同じ)。
- 本測定は emcc `-c` の通過までで、wasm link・実行は行っていない。
