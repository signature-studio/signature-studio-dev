<!-- 自動生成: python3 tools/liftdiff/tests/oob_top_frames.py > tools/liftdiff/results/m11_oob_top_frames.md (入力 = work/m11/batch_closure.jsonl・tools/m11/work/boot_final3.ll) (LD-18, #865) -->
# m11 OOB: 最上位 trap frame 上位 5 種の原因候補 (LD-18, #865)

対象 = wasm_trap のうち detail が "memory access out of bounds" の関数 239 件 (batch jsonl)。
IR 分類は候補。機械語との突合・単体再走は行っていない (未確定)。

| 最上位 frame | 件数 | IR 分類 | 呼出連鎖 (先頭 4) |
|---|---:|---|---|
| function_414ad0 | 68 | ptr_arg (inttoptr %arg 経由の deref あり) | function_414ad0 < function_414bb0 < function_662680 < function_63b880 |
| __asm_rep_movsq_memcpy | 13 | IR なし | __asm_rep_movsq_memcpy < function_4128b0__lifted < function_4128b0 < function_412a40 |
| function_412e40 | 12 | arg_val (%arg を値として使用のみ) | function_412e40 < function_419f60 < function_41a1a0 < function_41a3d0 |
| function_4133f0 | 11 | ptr_arg (inttoptr %arg 経由の deref あり) | function_4133f0 < function_446bb0 < function_95b400 < globalThis.__ld_call |
| function_1062930 | 11 | arg_val (%arg を値として使用のみ) | function_1062930 < function_10628a0 < function_11c8da0 < function_11c8eb0 |
