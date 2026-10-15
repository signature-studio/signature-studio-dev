# ildsp REPORT 付録: vtable slot 4 (0x1aa3a0) の lift と native 差分 (#2529)

`REPORT.md` §6 の全文 (250 行上限のため分割移動)。手順・実測・未解決の正本はこのファイル。

## 6. vtable slot 4 (0x1aa3a0) の lift と native 差分 (#2529)

既知類型との関係: 該当なし (D19 は 0 件ループの誤実行。count1=0 (36 件)・count2=0 (54 件) の経路を検査し不発。D1a・D1b はフラグを使わないため対象外)。
検証起点 commit: `ce53db8e` (origin/main)。測定 commit (コードを変えた最後の commit): `4d2eb9ca` (`fix(ildsp): take external tool paths from env (no literal /opt) (#2529)`)。前版 `9925f506` (外部ツールの既定パスを lift.sh に直書き) でも同じ結果 (240/240・ネガコン 2 件 FAIL) を 1 回確認済み。

### 結論 (1 行)
GeneralPitchShifter vtable slot 4 (RVA 0x1aa3a0・42 命令・直接 call / 間接 call 0) を RetDec で lift し、元の機械語との差分は 240/240 で一致。ネガティブコントロール 2 件は期待どおり FAIL。

### 選定根拠 (実測値)
| 候補 | 規模 | 判断 |
|---|---|---|
| A: CreateInstance 単独 closure | 36 関数・961 命令 (`ildsp_closure.json` の entry_only)。IAT (HeapAlloc・GetLastError 等) と SEH 系を含み、間接 call 4 件 (0x1aedc0 の 3 件・0x1b6f4c の 1 件) を含む | 1 run の上限に収まらない → 子 [T-SH-62] #3300 |
| B: 転送先 | 0x161fc0 = 324 命令・直接 call 15 / 0x162760 = 395 命令・直接 call 7・間接 `jmp rdx` 1 / 0x162f90 = 730 命令・直接 call 9 | 子 [T-SH-61] #3299 |
| **採用: slot 4 (0x1aa3a0)** | 42 命令・直接 call 0・間接 0・SIMD 0・rip 相対 0 | vtable の内部状態初期化。最小で完結する単位 |

候補 A の 961 命令は REPORT.md §4-5 の 924 命令 (関数範囲の線形走査) と数え方が一致せず、照合していない (#3300 で統一する)。

### closure 規模 (採用単位)
| 項目 | 値 |
|---|---:|
| 関数 | 1 (0x1aa3a0–0x1aa46c、0xCC B、42 命令、末尾 `ret`) |
| 直接 call / 間接 call / 間接 jmp | 0 / 0 / 0 |
| SIMD 命令 / rip 相対参照 | 0 / 0 |
| 条件分岐 (範囲内, 直接) | 4 (ループ 2 本の head 判定と継続) |
| store | ループ1 は count1 回 × 3 本、ループ2 は count2 回 × 2 本、固定 9 本 (qword 0x284・0x29c・0x290・0x2a8・[rdx]、dword 0x28c・0x2a4・0x298・0x2b0) |

### 手順 (`tools/shared/lift/ildsp/`)
1. `locate.py`: pefile で vtable (RVA 0x3dfcf8) の slot 4 = VA 0x1801aa3a0 を確認し、0xCC B を file offset 経由で切り出す。capstone で 42 命令・末尾 `ret`・call/jmp 0 を検算 (失敗で exit 1)。
2. RetDec: `--select-ranges 0x1801aa3a0-0x1801aa46c --select-decode-only` で `function_1801aa3a0` (1 関数、IR 175 行)。`gen_helpers.py` は使わない。根拠は x86 側の数値: 42 命令の内訳は cmp 4・inc 2・jl 2・jle 2・lea 2・mov 24・nop 4・ret 1・xor 1 (capstone・sha1 `63fa84fd5c82`)。CreateInstance closure の IR で `__asm_*` として残った命令 (#3318 本文: int3・movapd・movaps・movntps・movq・movups・punpcklbw・sfence) は 0 件、xmm/ymm/zmm の operand は 0 件、call/jmp は 0 件。IR 内の `__asm_` の件数は toolchain-retdec 未取得のため未計測。
3. `tools/shared/lift/libkio/ir_normalize.py` → emcc (`-O1 STANDALONE_WASM`、export `function_1801aa3a0`、854 B)。
4. `diff_test.py` (seed 0x2529、240 件): inner 0x2f8 B は全バイト乱数。count1 は {0,1,2,3,7,16}、count2 は {0,1,2,5} から選ぶ。ポインタ 5 欄 (+0x10・+0x18・+0x20・+0x258・+0x260) には 64 dword の buffer を張る。wrapper 16 B (+8 = inner)。`native_ref.c` は元の機械語を RWX mmap して `ms_abi` で直接呼ぶ。`run_wasm.mjs` は同じ case を wasm 線形メモリで実行する。
5. 比較: 呼出し後の inner 全バイト + wrapper 16 B + 全 buffer。ポインタ 5 欄と wrapper+8 は両側で 0 に正規化。全件一致かつ gate (count1=0 / count1>0 / count2=0 / count2>0 が各 1 件以上) で exit 0。

### 検証範囲 / 範囲外
- 範囲内: slot 4 の 42 命令 (ループ 2 本の count≤0 と count>0 の両経路、固定 9 store、ポインタ欄の参照)。入力は inner の全バイト乱数と count の境界値。
- 範囲外: slot 1–3・5 (未 lift)、間接 call 4 件 (closure 外)、CreateInstance 本体、vtable 経由の呼出し元の検証、count が負の経路 (仕様の集合外)。起動・GUI は本件に関わらないため KPI は対象外。

### 実測 (測定 commit `4d2eb9ca`、4 core、機械語 fn.bin sha1 `63fa84fd5c82`、入力 sha256 `f4b23b0f…`)
| 項目 | 結果 |
|---|---|
| コマンド | `RETDEC_BIN=[RETDEC]/bin/retdec-decompiler EMSDK_ENV=[EMSDK]/emsdk_env.sh FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/ildsp/lift.sh all` |
| 所要 (all, 3 回) | 6.490 / 6.530 / 6.501 s (min–max 6.49–6.53 s)。load 0.12→0.19 / 0.19→0.31 / 0.31→0.37 |
| ok | TOTAL 240/240、RESULT: PASS (count1=0 36/36、count1>0 204/204、count2=0 54/54、count2>0 186/186、TRAP 0)。単独 2.29 s |
| neg-compare (wasm 結果 record 0 の 1 バイトを反転) | TOTAL 239/240、RESULT: FAIL、exit 1 (期待どおり) |
| neg-ir (ループ2 の buffer store `store i32 0, ptr %44` を `1` に、IR 1 箇所) | TOTAL 54/240、不一致 186 = count2>0 の件数 (count2=0 の 54 件は一致)、RESULT: FAIL、exit 1 (期待どおり) |
| all | ALL OK (3 回とも exit 0) |

記入時点の HEAD は `d2b4cebe` (main 取り込みの merge commit)。実行コードの差分は 0 行: `git diff 4d2eb9ca HEAD -- tools/shared/lift/ildsp ':!tools/shared/lift/ildsp/REPORT*.md'` の出力は 0 行。`tools/shared/lift/libkio`・`tools/shared/env.sh` も `git diff 4d2eb9ca HEAD -- <範囲>` の出力は 0 行。`REPORT*.md` の差分は文書のみ (`git diff --stat 4d2eb9ca HEAD -- tools/shared/lift/ildsp` は REPORT.md の 1 ファイル。main 取り込みで REPORT.md に §5 (WaveformColouring) が加わった)。従って再測定は不要 (`docs/WORKFLOW.md` §6)。上の実測表は測定 commit `4d2eb9ca` の値で、差分指摘の修正 run (2026-10-15) では toolchain-retdec・toolchain-emsdk が `$ARTIFACTS_DIR` に無く (`fl-win64` のみ)、`lift.sh` は再実行していない。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 call 4 件 (0x1aedc0 の 3 件・0x1b6f4c の 1 件) の扱い | 候補 A の closure を完全に検証できない | trap 化 → 子 #3318 [T-SH-65] (#3300 の子)・到達実測 → 子 #3250 [T-SH-54] (#2528 の子) |
| slot 1–3 (0x161fc0・0x162760・0x162f90) の lift と差分 | vtable の残り method が未 lift | 子 #3299 (T-SH-61) |
| slot 5 (0x1aa470, `xor eax,eax; ret`) | 本 PR に含めない | 子 #3299 (T-SH-61) に移した (同 issue の受入条件 5) |
| CreateInstance 本体 (候補 A、36 関数・961 命令) | 本 PR の範囲外 | 子 #3300 (T-SH-62) |
| 候補 A の命令数: 961 (`ildsp_closure.json`) と 924 (REPORT.md §4-5) の数え方の不一致 | 選定根拠の数値の正本が未確定 | 子 #3300 (数え方を統一) |
