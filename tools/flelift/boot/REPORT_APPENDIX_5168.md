# REPORT_APPENDIX_5168 (PY-4877・patternCount 直接呼出し)

REPORT.md §14 の分割移動先。測定値・経緯はここ。

## 14. #5168 (PY-4877): boot 後に patternCount (0xd64d40) を直接呼ぶ driver

- **結論**: driver は動く (`fle_py_pattern_count` が boot 停止後に 0xd64d40 を `fle_run` で実行する)。boot 後の `patternCount` 呼出しで述語 0x12d8d30 が i=1..999 の順に呼ばれることを観測した (前回の「述語は boot 中に呼ばれない」は boot 中の話で、boot 後の呼出しでは届く)。ただし `patternCount` 内の間接呼出し (call site ret=0xd64d7a) が icall-miss (`dispatch(0)` → 戻り値 0) になり、`patternCount` の戻り値 0 は実行結果として信用できない。受入 1 (E[1..999] の実測) は未達。

| 項目 (測定 commit `8613de75b`) | 結果 |
|---|---|
| 1 回目 (`py4877_pred_e_probe.sh`・外側 110 秒上限) | rc 124 (build 完了後、boot の途中で時間切れ)。次の 580 秒の実行は `head` で打ち切られ rc 141 (SIGPIPE・boot 本体は無関係) |
| 2 回目 (`py4877_pred_e_probe.sh` の既定 run・`work/boot/run_py4877_probe.log`) | `FLEBOOT_PY4877_PRE` 非 0 行 0 → `FLEBOOT_PY4877_CALL {"ret":0,"threw":null}` → `FLEBOOT_PY4877_POST` 非 0 行 0 |
| 述語 0x12d8d30 | `[PY4877-PC]` n=999 (ecx=i が 1..999 の順・run_py4877_probe.log) |
| 間接呼出し | `[fleboot][ff] dispatch(0) -> ret 0 (m11 icall-miss 揃え, call site ret=0xd64d7a)` |
| boot 本体 | units_run 895・`boot_threw` exit (既存の KPI と同じ・変化なし) |

- **読み**: 呼出し前後とも `E[1..999]` は全 0 で、述語は 999 回呼ばれたが、`patternCount` の戻り値は icall-miss による 0 である。0 は「999 件を数えた」でも「0 件」でもなく、観測不能。E の内容が実起動で崩れるかは、この icall-miss を解消してから判定する。
- 未解決: icall-miss (0xd64d7a の間接呼出し先) の解消 → 親 #5168 の残件。boot 本体の KPI は変えていない。
