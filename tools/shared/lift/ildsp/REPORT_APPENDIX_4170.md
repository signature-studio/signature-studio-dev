# ildsp REPORT 付録: WaveformColouring vtable slot 0–5 の全呼出の native 対 wasm 差分 (#4170 / T-SH-100)

親 #3274 (T-SH-57)。前提は #4169 (`REPORT_APPENDIX_4169.md`・closed)。harness は `lift_wc6.sh` (`lift_wc.sh` を環境変数で差し替え、既定は変えない)。

## 1. 結論

- CreateInstance → slot 0・1・2・3・4・5 の順に 6 slot 全てを呼び、native (元の機械語) と wasm の戻り値・import 呼出回数・heap (arena)・.data を全 64 case でバイト比較した。**本検査 PASS 64/64・neg-cmp FAIL 64/64 (期待通り)**。
- 既定の入力 (`WC_CALL_ARGS` 未指定 = 全 slot `IN 0 0 0`) では native が 64/64 で SIGSEGV する (§3)。#4169 §4 の最小引数を slot 1・4 に入れて解消した。
- 引数は native が落ちない最小条件であり、FL 本体の実際の呼出側の値は**未確認** (#4169 §5)。slot 2 の `xmm1` も未制御。

## 2. 引数 (lift_wc6.sh)

| slot | RVA | RDX | R8 | R9 | S5 (5 番目) | 出典 |
|---|---|---|---|---|---|---|
| 0 | 0x1a9cf0 | IN | 0 | 0 | 0 | 既存の差分 harness と同じ |
| 1 | 0x1a9f10 | IN | OUT | 0 | 0 | #4169 §4 (R8 = 出力) |
| 2 | 0x1a9e10 | IN | 0 | 0 | 0 | #4169 §4 (全 0 で完走) |
| 3 | 0x1a9de0 | IN | 0 | 0 | 0 | #4169 §4 (全 0 で完走) |
| 4 | 0x1aa0b0 | IN | 0 | 0 | OUT | #4169 §4 (S5 = 出力・R8 = frame 数 0) |
| 5 | 0x1ac460 | IN | 0 | 0 | 0 | #4169 §4 (全 0 で完走) |

戻り値の畳み込み: `WC_RET_IDX="0 1 2 3 5"` (slot 4 を外す。戻り値は ABI 上未定義・REPORT_APPENDIX_3401.md §8-4)。

## 3. 実測 (測定 commit `4a18878ec`)

| 条件 | native | 差分 harness |
|---|---|---|
| `WC_CALL_SLOTS=6` (既定の引数 `IN 0 0 0`) | SIGSEGV 64/64 (addr=0x0) | 比較 0 件・rc 1 |
| `lift_wc6.sh ok` (本検査) | SIGSEGV 0・crash 0 | PASS 64/64・FAIL 0・traps 0・rc 0 |
| `lift_wc6.sh neg-cmp` (wasm 結果の arena 先頭 1 バイト反転) | crash 0 | PASS 0・FAIL 64・rc 1 (期待通り) |
| `lift_wc6.sh all` | | ALL OK |

- 本検査: elapsed 2.23 s・load 0.70 0.51 0.21 (開始・終了とも)。
- neg-cmp: elapsed 2.24 s・load 0.70 0.51 0.21 → 0.72 0.52 0.21。
- x64c: functions 60・insns 2,656・unsup 0・unlifted callees 0・imports 18・traps 0。wasm 172,024 B。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL 本体の呼出側の実引数 (slot 1 の R8 出力番地・slot 4 の S5 出力番地・frame 数) | 本検査の入力が native の最小条件であり、実際の呼出条件の網羅ではない | #4169 §5 (未確認)・親 #3274 の trace 項 |
| slot 2 の `xmm1` (浮動小数) の入力 | slot 2 の完走条件の網羅性 | #4169 §7 |
| 13 件目の HeapAlloc サイズ差 0x500 (PSOLA 側) | WaveformColouring の本件とは別の closure。本件では差 0 | #5162 |
