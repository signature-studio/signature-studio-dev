<!-- 自動生成: python3 tools/liftdiff/tests/trace_diverge_cd.py > tools/liftdiff/results/m11_unreachable_cd.md (LD-28 / #1035) -->
# m11 unreachable の型 C・D の原因候補 (LD-28, #1035)

対象 = trace_diverge_unreachable.py の型 C・D (食い違い観測のうち L の直接 call 先に分岐が無いもの・あるもの) 92 件。
原因候補 = 機械語の直接 call 先のうち IR の対応関数に無いもの (脱落候補) が、食い違いの次 entry に一致するかで判定。
call site と IR block は対応づけていない。P1・P2 は候補であり、確定ではない。

| 型 | 原因候補 | 件数 | 上位 関数 (件数) | 例 (batch 関数 / L / 原因関数) |
|---|---|---:|---|---|
| C | P3 未特定 (両側の次 entry とも IR に call あり) | 58 | 0x417b70 (32), 0x476c30 (8), 0x462ed0 (3) | 0x448d20 / 0x411d20 / 0x411d20 |
| C | P1 L 内の直接 call 脱落 (native の次 entry が IR に無い) | 9 | 0x4512b0 (2), 0x45b170 (2), 0x41c8c0 (1) | 0x63bef0 / 0x41c8c0 / 0x41c8c0 |
| D | P2 呼出元の直接 call 脱落 (native の次 entry が IR の呼出元に無い) | 20 | 0x41c820 (20) | 0x5c4360 / 0x418be0 / 0x41c820 |
| D | P3 未特定 (両側の次 entry とも IR に call あり) | 5 | 0x407e20 (2), 0x409470 (1), 0x418190 (1) | 0x680be0 / 0x407e20 / 0x407e20 |
