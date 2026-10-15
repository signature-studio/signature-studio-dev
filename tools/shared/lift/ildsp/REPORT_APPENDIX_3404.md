# ildsp REPORT 付録: vtable slot 5 (0x1aa470) の lift と native 差分 (#3404)

親 #3299 の受入条件 5 を範囲縮小で移したもの。slot 4 の手順 (`REPORT_APPENDIX_2529.md` §6) を流用し、戻り値の比較を加えた。手順・実測・未解決の正本はこのファイル。

既知類型との関係: 該当なし (ループ・フラグ・メモリ書込みを持たない 2 命令。D19・D1a・D1b の対象外)。
検証起点 commit: `6ae9d6c89` (origin/main)。測定 commit (コードを変えた最後の commit): `a8f449584` (`feat(ildsp): lift GeneralPitchShifter vtable slot 5 and compare its return value (#3404)`)。

### 結論 (1 行)
GeneralPitchShifter vtable slot 5 (RVA 0x1aa470・`xor eax,eax; ret`・2 命令) を RetDec で lift し、emcc で wasm 化した。native 実機械語との差分は 240/240 で一致 (戻り値 eax = 0 を含む)。ネガティブコントロール 2 件は期待どおり FAIL。

### 対象 (実測)
| 項目 | 値 |
|---|---|
| vtable (RVA 0x3dfcf8) の slot 5 | 0x1801aa470 (`locate.py` の検算で一致) |
| 機械語 | `33 c0 c3` (3 B・2 命令・直接 call / 間接 call / 直接 jmp 0)。後続は int3 の詰め物 |
| fn.bin sha1 | `2c4970053791676276ea7814b8d80555f3d32390` |
| 入力 | `block24360_PE.bin` sha256 `f4b23b0f…` |
| RetDec | `define i64 @function_1801aa470()`・`ret i64 0`・1 関数 (`--select-ranges 0x1801aa470-0x1801aa473`) |
| wasm | `function_1801aa470`・495 B (emcc 6.0.12・`-O1 STANDALONE_WASM`) |

slot 5 はメモリを読まず書かない。そのため記録の比較は戻り値だけが実質の検査になる。`locate.py` の `ret` 欄 (slot 5 = 1) で戻り値を比べ、slot 4 (void 扱い = 0) では比べない。

### 手順 (`tools/shared/lift/ildsp/`)
1. `GPS_SLOT=5` で `lift.sh` を起動する (既定は 4)。`locate.py <pe> <outdir> 5` が vtable slot 5 = VA 0x1801aa470 を確認し、3 B を切り出す (命令数 2・末尾 ret・call/jmp 0 を検算)。
2. RetDec `--select-ranges 0x1801aa470-0x1801aa473 --select-decode-only` → `libkio/ir_normalize.py` → emcc。
3. `diff_test.py` (seed 0x2529、240 件): inner 0x2f8 B・buffer 5 本 x 64 dword・wrapper 16 B を全バイト乱数で作る。count (+0x28・+0x244) は関数が読まないので gate は無い。
4. `native_ref.c` は元の機械語を RWX mmap し、ms_abi で直接呼ぶ。戻り値 (rax の下位 32 bit) を記録の ret 欄に書く。`run_wasm.mjs` は同じ case を wasm で実行し、戻り値の下位 32 bit を ret 欄に書く。
5. 比較: 記録 (status + ret + inner + wrapper + buffer) の全バイト。全件一致で exit 0。

記録形式は slot 4 と同じく全 slot 共通で、status (4 B) の次に ret (4 B) を置いた。slot 4 は ret を比べないので、0 のまま変わらない (`ranges.json` の `ret` で切り替え)。この変更で slot 4 の記録長は 2060 → 2064 B になった。slot 4 の結果は下の実測で再確認した。

### 実測 (測定 commit `a8f449584`・4 core)
| 項目 | 結果 |
|---|---|
| コマンド | `GPS_SLOT=5 RETDEC_BIN=<[RETDEC]>/bin/retdec-decompiler EMSDK_ENV=<[EMSDK]>/emsdk_env.sh FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/ildsp/lift.sh all` |
| 所要 (all, 3 回) | 6.544 / 6.582 / 6.525 s (min–max 6.525–6.582 s)。load 0.74→0.76 / 0.76→0.78 / 0.78→0.81 |
| ok | TOTAL 240/240、RESULT: PASS、TRAP 0 (戻り値 eax = 0 の一致を含む) |
| neg-compare (wasm 結果 record の ret 欄の下位 1 バイトを反転) | TOTAL 239/240、RESULT: FAIL、exit 1 (期待どおり。不一致 1 件 = case#0) |
| neg-ir (IR の `ret i64 0` を `ret i64 1` に、1 箇所) | TOTAL 0/240、RESULT: FAIL、exit 1 (期待どおり。全 240 件で戻り値が 1 と不一致) |
| all | ALL OK (3 回とも exit 0) |

同じ HEAD `a8f449584` で slot 4 (既定値) も 3 回測定した (記録形式変更の回帰確認)。

| 項目 | 結果 |
|---|---|
| all, 3 回 | 6.484 / 6.544 / 6.497 s。load 0.75→0.77 / 0.77→1.03 / 1.03→1.02 |
| ok | TOTAL 240/240、RESULT: PASS (count1=0 36/36・count1>0 204/204・count2=0 54/54・count2>0 186/186・TRAP 0) |
| neg-compare | TOTAL 239/240、RESULT: FAIL、exit 1 (期待どおり) |
| neg-ir (ループ2 の buffer store 0 → 1) | TOTAL 54/240、RESULT: FAIL、exit 1 (不一致 186 = count2>0 の件数。前回 slot 4 の実測と同じ) |
| all | ALL OK (3 回とも exit 0) |

fn.bin sha1 (slot 4) `63fa84fd5c82f8b5477def6849428b7b41b77e07`。

### 検証範囲 / 範囲外
- 範囲内: slot 5 の 2 命令の戻り値 (eax = 0)。入力はメモリ全体の乱数 (記録の全バイトで、関数が触らないことも確かめる)。
- 範囲外: slot 5 が「どの method か」(役割)。native で 0 を返すことは確かめたが、役割の確定は REPORT.md §4 の未解決 (slot 1–3・5 の役割) に残す。slot 1–3 の lift は #3299 の残件。

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot 5 の役割 (どの method か) の確定 | 戻り値 0 の実機械語は確認済み。役割は未確定 | REPORT.md §4 の未解決 (子 [T-SH-38]) |
| slot 1–3 (0x161fc0・0x162760・0x162f90) の lift と差分 | vtable の残りの method が未 lift | 親 #3299 [T-SH-61] の移送先 |

KPI: 起動・GUI に関わらないため対象外。
