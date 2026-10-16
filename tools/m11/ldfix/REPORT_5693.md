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

## 4. 未測定 (受入条件の残り)

- **wasm 直接呼びで unit の結果が変わらないこと**: 本 run には `toolchain-emsdk` が無く (`oc_artifacts` に無い)、
  emcc で wasm を作れないため未測定。既定 OFF のため、既定の IR・unit 結果は変わらない。
  適用して測るには `toolchain-emsdk` を含む `oc_artifacts` で再起動する必要がある。
- `m11_gen_ir2.sh` の既定 IR への組込み (`M11_FIX_439F90=1` を既定にする判断) は、unit 測定の後の別判断。

## 5. 検証の限界

- 機械語との照合は `mismatch_5436.py` の件数 (呼出し件数) による。block 単位の完全一致は取っていない。
- `clang -c` で新 IR が構文・型として通ることを確認した (警告は triple の上書きのみ)。
- 旧 IR の `0x44ba40` 呼出し件数が 2 件でない IR には適用しない (fail-closed)。
