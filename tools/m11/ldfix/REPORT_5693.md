# #5693 (CI-235): function_439f90 の IR を機械語どおりに戻す

親: #5688。対象: `0x439f90` (IR_FEWER 3・機械語 4 / IR 2)。

## 1. 結論

- `fix_439f90.py` で `function_439f90` を機械語 (0x439f90〜0x43a177) の基本ブロックどおりに組み直した。
- 判定器の実測: `mismatch_5436.py` の MISMATCH **13 → 10** (`0x439f90` の IR_FEWER 3 件が消えた)。
  判定 `judge_copy_3382.py` の MISMATCH も 13 → 10 (受入条件の「10 以下」を満たす)。
- 既定 OFF (`M11_FIX_439F90=1` で適用)。wasm 直接呼びの unit 結果は **未測定** (§4)。

## 2. 欠落の内容 (機械語との突合)

`boot_final3.ll` の旧 `function_439f90` が機械語と違う点:

| 機械語 | 旧 IR |
|---|---|
| `[rbx]` (arg2 のセル) を読んで比較・使う (`439fb0`・`439fba`) | `arg2` を値として扱う (load が無い) |
| `439fe2` ループ更新: `add [rbx],2`・`word [rax]==si`・`add r13d,1`・`[rbx]` 更新 (`439fe2`〜`439fee`) | 無い。ループは `store`+`call 44ba40` の 1 組だけ |
| `43a094`〜`43a12f` の r13 != 1 経路 (`414ad0`・`414850`・`44ba40`・`409c80`) | 無い。`dec_label_pc_43a07f` の `413060` 1 経路だけ |

`0x44ba40` の呼出しは、機械語 4 件 (`439fd8`・`439ffb`・`43a0c9`・`43a121`) に対し、旧 IR は 2 件。
新 IR は 4 件 (`439fd8`・`439ffb`・`43a0cb`・`43a121` に対応) で、件数が一致する。

## 3. 再現 (作業ツリー HEAD = e7df3610f)

```
python3 tools/m11/ldfix/fix_439f90.py tools/m11/work/boot_final3.ll OUT.ll     # 1 回目のみ (二重適用は assert で止まる)
python3 tools/m11/ldfix/scan_spill_deref_3328.py OUT.ll --pe <PE> --out S.json
python3 tools/m11/ldfix/judge_copy_3382.py OUT.ll --pe <PE> --scan S.json --out J.json
python3 tools/m11/ldfix/mismatch_5436.py OUT.ll --pe <PE> --judge J.json
```

`<PE>` は `fl-win64` の `extracted/block00031_PE.bin` (`m11_gen_ir2.sh` の既定 PE。`block00000_PE.bin` は `.pdata` を持たない)。

### 測定値

| 指標 | 旧 (boot_final3.ll) | 新 (fix_439f90 適用) |
|---|--:|--:|
| judge MISMATCH | 13 | **10** |
| judge OK_ARGK | 10 | 13 |
| mismatch_5436 内訳 | THUNK 3・IR_FEWER 9・IR_MORE 1 | THUNK 3・IR_FEWER 6・IR_MORE 1 |
| `0x439f90` の MISMATCH 行 | 3 (IR_FEWER, machine 4 / IR 2) | 0 |

残 IR_FEWER 6 件は `0xf552a0` (`12df530` 6 件・機械 6 / IR 5) で、本 issue の範囲外 (#5688 の未解決)。

## 4. wasm unit 比較 (#5700) と既定 ON 判断

測定: `tools/m11/ldfix/fix_439f90_e2e.sh` (HEAD `292fc08ec`)。`toolchain-emsdk` (emcc 6.0.12) で既定 IR と `M11_FIX_439F90=1` の IR をそれぞれ wasm にし、942 unit を survey した。

| 項目 | 既定 IR | fix IR (`M11_FIX_439F90=1`) |
|---|---|---|
| IR 行数 | 490790 | 490876 (差分 258 行) |
| ir_sha256 | b202c157… | 578dd958… |
| wasm build | rc 0 (22 秒) | rc 0 |
| survey (ok / miss / halt0 / oob / noproc) | 873 / 47 / 6 / 15 / 1 | 873 / 47 / 6 / 15 / 1 |

- `survey_diff.py`: 遷移は全て同種 (ok→ok 873・miss→miss 47 ほか)。**ok 退行 0**。kind 以外の差分 0。icall の総数 [ok, miss] 差 0。
- e2e 全体: fail=0、所要 2 分 30 秒 (load 0.46 → 0.96、nproc 4)。

**解釈の限界**: unit 結果が一致したのは、`function_439f90` の差し替えが survey の 942 unit の結果に現れなかったことを示すだけ。
関数が unit から実際に呼ばれたかは**未測定**。呼出し元は `function_510750` (1 箇所) で、そこへの到達は静的に確認できなかった。
既存の計数手段 (`PROBES` 固定 index・`M11_INSTR_*`) に 439f90 の計測点は無く、足すと既定 build の出力が変わるため、本 run では計測 build を作らなかった。

**既定 ON の判断**: 既定 OFF のまま据え置く。理由は (1) 到達性が未確定で、差分が効いたかどうか分からない、(2) 機械語との突合は呼出し件数 (IR_FEWER 3→0) による近似で block 単位の完全一致は未確認、の 2 点。
既定 ON への変更は、到達性の計測 (wasm の `function_439f90` の入口計数) の結果を見てから別 PR で判断する。到達性の計測は #5715 ([CI-238]・親 #5700) で行う。

## 4b. 到達性計測 (#5715 / CI-238)

計測 build は opt-in (`M11_FIX_439F90=1`)。既定 build と既定 IR は変えていない。

- **入口計数**: `function_439f90` の入口に volatile store を 1 つ入れた (`ldfix/m11_439f90_probe_insert.py`)。
  呼出し無しの store のみ (survey を変えない・#1847)。実行は `ldfix/m11_439f90_reach.sh`、survey は
  `ldfix/m11_439f90_reach_survey.mjs`。結果は `ldfix/results/reach_439f90_5715.json` (unit 別・942 件)。
- **結果 (942 unit)**: `function_439f90` 入口に到達 **0 unit** / 未到達 **942 unit**。
  kind 内訳は ok 873・miss 47・halt0 6・oob 15・noproc 1。
- **陽性対照**: 同じ build で `function_417b70` (`m11_ov.c` が `M11_ENTRY_PROBE` で常に立てる probe) は **21 unit** で到達。
  計数の仕組みが動いていることの確認。
- **読み**: 直接の呼出し元は `function_510750` (IR 185554 行) と間接 call 表の trampoline (`m11_tr_function_439f90`) の 2 つ。
  どの unit でも入口計数が立たないため、この 942 unit の実行では `function_439f90` は呼ばれない。
  `function_510750` 自体の到達は本計測では測っていない (未測定)。
- **build 上の注意**: 計測 build は `m11_build.sh` の既定と同じ link に `m11_439f90_probe_rt.c` を足しただけ。
  `m11_entry_probe.sh` の 8 関数固定 probe は使わない (439f90 を含まないため)。
- **残り (本 issue の範囲外)**: 既定 ON への変更は別判断。`function_510750` の到達計測は別 issue が要る。

## 4a. 未測定 (旧記述の解消)

- 旧 §4 の「wasm 直接呼びで unit の結果が変わらないこと」は、`toolchain-emsdk` を素材に含めた本 run で
  emcc build が通ったため計測可能になった。unit 結果 (ok/miss 件数) の既定 IR との比較は本 run では行っていない
  (入口計数の目的は到達の確認で、既定 OFF のままの判断材料)。
- `m11_gen_ir2.sh` の既定 IR への組込み (`M11_FIX_439F90=1` を既定にする判断) は、到達が確認できていないため行わない。

## 5. 検証の限界

- 機械語との照合は `mismatch_5436.py` の件数 (呼出し件数) による。block 単位の完全一致は取っていない。
- `clang -c` で新 IR が構文・型として通ることを確認した (警告は triple の上書きのみ)。
- 旧 IR の `0x44ba40` 呼出し件数が 2 件でない IR には適用しない (fail-closed)。
