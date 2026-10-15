# ildsp GeneralPitchShifter_CreateInstance 単独 closure の RetDec 入力と census (T-SH-62 #3300)

親: #2529 (T-SH-39)。範囲縮小の経緯は #3300 本文。wasm 化は [T-SH-65] #3318、native 差分は [T-SH-66] #3320。

既知類型との関係: 該当なし (入力作成と census のみ。wasm 化と差分は未実施。RetDec の分岐複製は下の §3 で未分類の観察として記録)。
測定 commit: `0d81e174` (スクリプトを入れた最後のコード commit)。`git diff 0d81e174 HEAD -- tools/shared/lift/ildsp ':!*.md'` の出力は空 (差分 0)。

## 結論 (1 行)
closure は 36 関数・961 命令・間接 call 10 件で、RetDec の範囲入力と IR の define 検査は通る。IR の外部宣言は IAT 10 種・画像内ポインタ 3 種・SSE helper 8 種で、wasm 化 (#3318) と native 差分 (#3320) が残る。

## 1. 再現
```
FL_WIN64_DIR=<fl-win64 展開先> RETDEC_BIN=<retdec-decompiler> bash tools/shared/lift/ildsp/ci_lift.sh
```
- `ci_ranges.py`: entry 0x1aa290 から直接 call と .text 内の直接 jmp を辿る (`ildsp_closure.py` の closure() と同じ規則)。出力は 36 関数・961 命令・間接 call 10 (x86 の capstone 走査)。値が一致しなければ exit 1。
- `ci_lift.sh`: 範囲 (VA 形式) を `retdec-decompiler --select-ranges --select-decode-only` に渡す。
- `ci_census.py`: IR (`ci.drc.ll`) の define と宣言を範囲と照合する。範囲の関数が 1 つでも define されていなければ exit 1。

### 実測 (測定 commit `0d81e174`・4 core・n=3)
| 項目 | 値 |
|---|---|
| `ci_lift.sh` の実行時間 (ranges + RetDec + census) | 2.136–2.156 s (min–max。2.145 / 2.136 / 2.156) |
| load (実行前) | 0.10–0.17 |
| 3 回の出力 | 1・2 回目は `cmp` で一致 (census と ranges の出力) |

## 2. 結果 (実測)
| 項目 | 値 | 数え方 |
|---|---:|---|
| 範囲の関数数 | 36 | `.pdata` 24 + `.pdata` の無い葉 12 (近似: 次の `.pdata` 先頭まで) |
| 命令数 | 961 | 到達関数の命令開始 RVA の和集合 |
| x86 の間接 call | 10 | 範囲内の `call` で即値でないもの (capstone) |
| RetDec の define | 45 | 範囲 36 + 範囲外の追加 9 (`function_1801af090`〜`af0e8`。IR 内に参照なし) |
| 範囲の define 欠落 | 0 | entry は export 名 `GeneralPitchShifter_CreateInstance` で出る |

### 2-1. IR の外部宣言 (範囲内の呼び出し行数)
| 種別 | 名前 (IR 行数) |
|---|---|
| IAT (10 種) | FlsSetValue 5・HeapAlloc 2・FlsGetValue 2・GetLastError 2・HeapFree 1・EnterCriticalSection 1・LeaveCriticalSection 1・RaiseException 1・RtlPcToFileHeader 1・SetLastError 1 |
| 画像内ポインタ (3 種) | function_1801cb5e0 1 (slot 0x268260)・function_1801cb600 1 (slot 0x268268)・function_1801aef40 1 |
| SSE helper `__asm_` (8 種) | movaps 7・movntps 8・movups 3・int3 4・movapd 1・movq 1・punpcklbw 1・sfence 1 |

### 2-2. 間接 call 4 件 (REPORT_CLOSURE §4.6 と同じ 4 件)
範囲内にある 4 件は 0x1aedf6 (画像内 0x268260 → `function_1801cb5e0`)・0x1aee04 (IAT RtlPcToFileHeader)・0x1aee4a (IAT RaiseException)・0x1b6f6c (画像内 0x268268 → `function_1801cb600`)。残り 6 件は IAT (0x1b882f・0x1b88cf・0x1b9061・0x1b909a・0x1b90a4・0x1b9c5a)。

## 3. 検算と注
- 検算 (別算法): x86 の間接 call は capstone の走査で 10 件 (`ci_ranges.py`)。`ildsp_closure.py` の entry_only.indirect_calls = 10 と一致。
- **IR の呼び出し行数は x86 件数と一致しない**。RetDec が分岐ごとに同じ命令を複製する (例: 0x1b8820 の FlsSetValue は IR 4 行、x86 は 2 箇所)。IR の行数で件数を照合しない (`ci_census.py` の注)。
- 範囲外の追加 define 9 件は IR 内に参照が無い。wasm 化では gc で落ちる見込み (未確認)。

## 4. ネガティブコントロール
| 名前 | 壊し方 | 結果 |
|---|---|---|
| neg_rename | `ci.drc.ll` の `function_1801ac9c0` の define 名を変更 (`neg.ll`) | `FAIL: 範囲の関数が define されていない: ['function_1801ac9c0']`・rc 1 |

## 5. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| IAT 10 種の stub 化の方針 (C 実装か wasm import か) | wasm 化 | [T-SH-65] #3318 |
| SSE helper 8 種 (`__asm_`) の C 実装。`gen_helpers.py` は未対応で exit 1 | wasm 化 | [T-SH-65] #3318 |
| 間接 call 4 件の trap 化 (ac 4) | 正常系の到達 | [T-SH-65] #3318 (到達実測は #3250) |
| 全バイト差分・ネガティブコントロール・gate | 受入の残り | [T-SH-66] #3320 |
| 範囲外の追加 define 9 件の由来 | 定義の意味は未確認 | [T-SH-65] #3318 |
| `.pdata` の無い葉 12 件の範囲 (次の `.pdata` 先頭まで) | 命令数は上限側に偏りうる | #161 |

## 6. 検証範囲 / 範囲外
- 範囲: 範囲の再現・RetDec の定義生成・census。コードは HEAD で再実行して ALL OK を確認。
- 範囲外: wasm 化・native 実行・差分・gate (子へ)。RetDec の出力 IR の意味論は未検証。
