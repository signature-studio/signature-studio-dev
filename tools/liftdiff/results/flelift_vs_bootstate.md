新 boot 状態: 関数数 7421 — 一致 4182 / 不一致 741 / 実行不能 2498
旧 boot 状態 (17 unit):        一致 4143 / 不一致 633 / 実行不能 2645

verdict 遷移 (旧 → 新):
  match     → mismatch     200
  mismatch  → match        139
  unexec    → mismatch     132
  unexec    → match        125
  mismatch  → unexec        85
  match     → unexec        25

実行不能 reason 内訳 (新 → 旧):
  native_fault_all_patterns           1244 →  1158
  native_null_deref_all_patterns       494 →   691
  no_wasm_definition                   389 →   389
  hang                                 321 →   357
  unsupported_sig                       50 →    50
