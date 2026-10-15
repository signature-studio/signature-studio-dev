# ildsp GeneralPitchShifter_CreateInstance 単独 closure の RetDec 入力と census (T-SH-62 #3300)

親: #2529 (T-SH-39)。範囲縮小の経緯は #3300 本文。wasm 化は [T-SH-65] #3318、native 差分は [T-SH-66] #3320。

既知類型との関係: 該当なし (入力作成と census のみ。wasm 化と差分は未実施。閉包の取りこぼしは §2-2 で未分類の観察として記録)。
測定 commit: `d69ab303` (census・ci_ranges・ci_lift の最後のコード commit)。`git diff d69ab303 HEAD -- tools/shared/lift/ildsp ':!*.md'` の出力は空 (差分 0)。

## 結論 (1 行)
closure は 36 関数・961 命令・間接 call 10 件で、RetDec の範囲入力と IR の define 検査は通る。ただし closure は条件分岐と計算ジャンプの先を辿らず、範囲外の直接呼び出し先 1 件と計算ジャンプ表の飛び先 9 件が IR に残る (§2-2)。wasm 化 (#3318) と native 差分 (#3320) が残る。

## 1. 再現
```
FL_WIN64_DIR=<fl-win64 展開先> [RETDEC_BIN=<retdec-decompiler>] bash tools/shared/lift/ildsp/ci_lift.sh
```
- `RETDEC_BIN` 未設定なら PATH の `retdec-decompiler` を使う (外部ツールの場所は docs/REFERENCES.md §4)。
- `ci_ranges.py`: entry 0x1aa290 から直接 call と .text 内の直接 jmp を辿る (`ildsp_closure.py` の closure() と同じ規則)。出力は 36 関数・961 命令・間接 call 10 (x86 の capstone 走査)。値が一致しなければ exit 1。範囲内の直接分岐のうち範囲外の飛び先を `outside_targets` に出す (jcc を含む)。
- `ci_lift.sh`: 範囲 (VA 形式) を `retdec-decompiler --select-ranges --select-decode-only` に渡す。
- `ci_census.py`: IR (`ci.drc.ll`) の define と宣言を範囲と照合する。範囲の関数が 1 つでも define されていなければ exit 1。declare のみの呼び出し先は、`outside_targets` の飛び先なら「範囲外の直接呼び出し先」、それ以外は「画像内ポインタ」に分ける。

### 実測 (測定 commit `d69ab303`・4 core・n=3)
| 項目 | 値 |
|---|---|
| `ci_lift.sh` の実行時間 (ranges + RetDec + census) | 2.155–2.180 s (min–max。2.179 / 2.155 / 2.180) |
| load (実行前) | 0.02–0.10 |
| 3 回の出力 | 3 回とも `cmp` で一致 (rc 0・ALL OK) |

## 2. 結果 (実測)
| 項目 | 値 | 数え方 |
|---|---:|---|
| 範囲の関数数 | 36 | `.pdata` 24 + `.pdata` の無い葉 12 (近似: 次の `.pdata` 先頭まで) |
| 命令数 | 961 | 到達関数の命令開始 RVA の和集合 |
| x86 の間接 call | 10 | 範囲内の `call` で即値でないもの (capstone) |
| x86 の範囲外直接分岐の飛び先 | 1 | `outside_targets`。0x1aefa7 `jne` → 0x1aef40 (§2-2 (a)) |
| RetDec の define | 45 | 範囲 36 + 範囲外の追加 9 (計算ジャンプ表の飛び先。§2-2 (b)) |
| 範囲の define 欠落 | 0 | entry は export 名 `GeneralPitchShifter_CreateInstance` で出る |

### 2-1. IR の外部宣言 (範囲内の呼び出し行数)
| 種別 | 名前 (IR 行数) |
|---|---|
| IAT (10 種) | FlsSetValue 5・HeapAlloc 2・FlsGetValue 2・GetLastError 2・HeapFree 1・EnterCriticalSection 1・LeaveCriticalSection 1・RaiseException 1・RtlPcToFileHeader 1・SetLastError 1 |
| 画像内ポインタ (2 種) | function_1801cb5e0 1 (呼び出し元 0x1aedc0・x86 の間接 call 0x1aedf6・slot 0x268260)・function_1801cb600 1 (呼び出し元 0x1b6f4c・x86 の間接 call 0x1b6f6c・slot 0x268268) |
| 範囲外で define の無い直接呼び出し先 (1 種) | function_1801aef40 1 (呼び出し元 0x1aef60・x86 の飛び元 0x1aefa7 `jne`) |
| SSE helper `__asm_` (8 種) | movaps 7・movntps 8・movups 3・int3 4・movapd 1・movq 1・punpcklbw 1・sfence 1 |

### 2-2. 閉包の取りこぼし (未解決・#3318 で扱う)
closure は `call` と直接 `jmp` だけを辿る。そのため次の 2 種が範囲に入らない。どちらも x86 で確認した。
- **(a) 条件分岐の先の直接呼び出し先 (1 件)**: 0x1aefa7 `jne 0x1801aef40` (閉包関数 0x1aef60 の中)。0x1aef40 は `.pdata` の無い 16 バイトの `rep stosb` ヘルパ (`push rdi; mov eax,edx; mov rdi,rcx; mov rcx,r8; rep stosb; mov rax,r11; pop rdi; ret`)。IR では `declare` だけがあり、0x1aef60 の本体から `call @function_1801aef40` で呼ばれる。`ci_census.py` は「範囲外で define の無い直接呼び出し先」として別行に出す。
- **(b) 計算ジャンプの表の飛び先 (9 define)**: 0x1af08b `jmp r9`。r9 は 0x1af07a の `mov eax, dword ptr [r9 + r8*4 + 0x442000]` と `add r9, rax` で求める。表 0x442000 (`_RDATA`) の k = 0〜16 の 32 bit 値が RVA の 17 件 (k = 17〜19 は 0。k = 20 以降は別の値で、この表の対象外)。17 件のうち 9 件は RetDec の define の先頭 (`function_1801af090`・`af0a0`・`af0a8`・`af0b0`・`af0c0`・`af0cc`・`af0d0`・`af0e0`・`af0e8`)、残り 8 件は case 本体の途中 (0x1af094・0x1af097・0x1af09b・0x1af09e・0x1af0a4・0x1af0b4・0x1af0c4・0x1af0c7)。したがって 9 define は未到達のバイトではなく、0x1aef60 の計算ジャンプの飛び先である。IR の 0x1aef60 本体に `indirectbr`・`switch`・`unreachable` は無く、9 define はどの `call` からも参照されない (census の「IR 内の call 参照 0 件」)。RetDec がこの表を解いたかは IR から確認できていない (未確認)。
- 閉包規則を変える (jcc と計算ジャンプの表を辿る) と 36 関数・961 命令が変わるので、再測定を伴う。判断は #3318 で行う。

## 3. IR の呼び出し行数と x86 件数
- **IR の呼び出し行数は x86 の件数と一致しない** (`ci_census.py` の注)。例: FlsSetValue の IR 5 行 = `function_1801b8820` の 4 行 (x86 の `call 0x1801b9334` が 0x1b8865・0x1b8892・0x1b88a3・0x1b88b4 の 4 箇所。件数は一致) + サンク本体 `function_1801b9334` の 1 行 (`jmp qword ptr [rip + IAT]` が define になる)。
- IAT の `jmp [IAT]` サンクは直接 call で呼ばれる。0x1b932c (FlsGetValue) と 0x1b9334 (FlsSetValue) は `call` の直接の先 (0x1b932c は 1 箇所、0x1b9334 は 4 箇所)。0x1bb426 (EnterCriticalSection) と 0x1bb47a (LeaveCriticalSection) は、直接 call される小関数 0x1bb414 と 0x1bb468 の末尾の `jmp [IAT]`。これらは x86 の `call [IAT]` ではないので、間接 call 10 件に入らない。
- 間接 call 4 件 (0x1aedf6 → 0x268260 / 0x1aee04 → RtlPcToFileHeader / 0x1aee4a → RaiseException / 0x1b6f6c → 0x268268) は REPORT_CLOSURE §4.6 と同じ。残り 6 件は IAT (0x1b882f・0x1b88cf・0x1b9061・0x1b909a・0x1b90a4・0x1b9c5a)。
- 検算 (別算法): x86 の間接 call は capstone の走査で 10 件 (`ci_ranges.py`)。`ildsp_closure.py` の entry_only.indirect_calls = 10 と一致。

## 4. ネガティブコントロール
| 名前 | 壊し方 | 結果 |
|---|---|---|
| neg_rename | `ci.drc.ll` の `function_1801ac9c0` の define 名を変更 (`neg.ll`) | `FAIL: 範囲の関数が define されていない: ['function_1801ac9c0']`・rc 1 (測定 commit `d69ab303` の census) |

## 5. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| IAT 10 種の stub 化の方針 (C 実装か wasm import)。直接 call のサンク 2 種 (0x1b932c・0x1b9334) と末尾 jmp の 2 種 (0x1bb426・0x1bb47a) を含む | wasm 化 | [T-SH-65] #3318 |
| SSE helper 8 種 (`__asm_`) の C 実装。`gen_helpers.py` は未対応で exit 1 | wasm 化 | [T-SH-65] #3318 |
| 間接 call 4 件の trap 化 (ac 4) | 正常系の到達 | [T-SH-65] #3318 (到達実測は #3250) |
| 閉包の取りこぼし: 直接 jcc 先 function_1801aef40 (§2-2 (a))・計算ジャンプ表の 9 define (§2-2 (b))。閉包規則を変えるか。変えれば 36/961 が変わり再測定 | 範囲・wasm 化の意味 | [T-SH-65] #3318 |
| 全バイト差分・ネガティブコントロール・gate | 受入の残り | [T-SH-66] #3320 |
| `.pdata` の無い葉 12 件の範囲 (次の `.pdata` 先頭まで) | 命令数は上限側に偏りうる | #161 |

## 6. 検証範囲 / 範囲外
- 範囲: 範囲の再現・RetDec の定義生成・census。コードは HEAD で再実行して ALL OK を確認。
- 範囲外: wasm 化・native 実行・差分・gate (子へ)。RetDec の出力 IR の意味論は未検証。RetDec が計算ジャンプの表を解いたかは未確認 (§2-2 (b))。
